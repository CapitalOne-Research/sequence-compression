from typing import Any
from datetime import datetime

from c1.aiml.compression.utils.sizing import get_json_byte_size, _ensure_list
from c1.aiml.compression.utils.lookup import ENCODING_SCHEMES

_AUTO_MAX_DEPTH = 3
_AUTO_AUX_EMITTING = frozenset({"cat", "del", "quant", "stl", "tbqm", "tbqp"})
_AUTO_TERMINAL = frozenset({"bm", "bp", "nbp"})
_AUTO_DEFAULT_CANDIDATES = ("bm", "bp", "cat", "del", "nbp", "rle", "stl")
_AUTO_LOSSY_CANDIDATES = ("quant", "tbqm", "tbqp")

# Static (step, input_type) -> output_type table. "_terminal" means the step
# emits non-list output and cannot have children. Driving the DFS off this
# table avoids re-inferring types from the values list at every node.
_AUTO_TYPE_TRANSITIONS: dict[str, dict[str, str]] = {
    "bm":    {"binary": "_terminal"},
    "bp":    {"binary": "_terminal", "int": "_terminal"},
    "nbp":   {"binary": "_terminal", "int": "_terminal"},
    "cat":   {"string": "int"},
    "del":   {"int": "int"},
    "quant": {"float": "int"},
    "rle":   {"binary": "int", "int": "int", "string": "_terminal"},
    "stl":   {"int": "int"},
    "tbqm":  {"float": "int"},
    "tbqp":  {"float": "int"},
}

# Reverse index: input_type -> tuple of steps that accept it. Computed once.
_AUTO_VALID_FOR_TYPE: dict[str, tuple[str, ...]] = {}
for _step, _transitions in _AUTO_TYPE_TRANSITIONS.items():
    for _input_type in _transitions:
        _AUTO_VALID_FOR_TYPE.setdefault(_input_type, []).append(_step)
_AUTO_VALID_FOR_TYPE = {t: tuple(steps) for t, steps in _AUTO_VALID_FOR_TYPE.items()}


_AUTO_ROOT_SEEDS: dict[str, tuple[str, ...]] = {
    "binary":   ("bm", "nbp", "rle"),
    "int":      ("bp", "nbp", "rle", "del", "stl"),
    "float":    ("quant", "tbqm", "tbqp"),
    "string":   ("cat", "rle"),
}


def _infer_list_type(values: list) -> str:
    """Classify a list's element type for `auto_encode` applicability checks.

    Returns one of: 'empty', 'binary', 'int', 'float', 'string', 'datetime', 'mixed'.
    """
    if not values:
        return "empty"

    if all(isinstance(v, str) for v in values):
        try:
            for v in values:
                datetime.fromisoformat(v)
            return "datetime"
        except (ValueError, TypeError):
            return "string"

    if all(isinstance(v, int) for v in values):
        if all(v in (0, 1) for v in values):
            return "binary"
        return "int"

    if all(isinstance(v, (int, float)) for v in values):
        return "float"

    return "mixed"


# Human-readable labels for the improper-pipeline warnings surfaced in the UI.
_TYPE_LABELS = {
    "binary": "binary (0/1)",
    "int": "integer",
    "float": "float",
    "string": "string",
    "datetime": "datetime",
}
_SCHEME_LABELS = {
    "bm":    "bitmap (bm)",
    "bp":    "bit-pack (bp)",
    "cat":   "categorical (cat)",
    "del":   "delta (del)",
    "nbp":   "nullmap bit-pack (nbp)",
    "quant": "quantization (quant)",
    "rle":   "run-length (rle)",
    "stl":   "sentinel (stl)",
    "tbqm":  "turbo-quant MSE (tbqm)",
    "tbqp":  "turbo-quant prod (tbqp)",
}
_TYPE_ORDER = ("binary", "int", "float", "string")


def _accepted_types_phrase(step: str) -> str:
    """Readable list of the element types a step accepts, e.g. 'binary (0/1) or integer'."""
    accepted = _AUTO_TYPE_TRANSITIONS.get(step, {})
    labels = [_TYPE_LABELS[t] for t in _TYPE_ORDER if t in accepted]
    if not labels:
        return "no"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} or {labels[1]}"
    return ", ".join(labels[:-1]) + f", or {labels[-1]}"


def validate_pipeline(pipeline: str, list_type: str | None = None) -> list[dict]:
    """Flag improper encoding pipelines for a given data type, without encoding.

    Walks the pipeline left-to-right against the same `_AUTO_TYPE_TRANSITIONS`
    table the auto-search uses, so the warnings stay in lockstep with what the
    encoder actually accepts. Detects:
      - type_mismatch:     a step fed an element type it cannot encode
                           (e.g. `cat` on a non-string field, `bm` on ints).
      - not_terminal_last: a packing step whose output is a non-list value but
                           which is followed by more steps (e.g. `bp_cat`).
      - aux_repeat:        an aux-emitting step (cat/del/quant/stl) used twice.
      - unknown_scheme:    an unrecognised short code.
      - mixed_type:        the field mixes element types (field-level note).

    Args:
        pipeline: Underscore-joined scheme string (e.g. 'cat_rle_bp'). '' and
            'auto' return no warnings — pass-through and auto are always valid.
        list_type: Inferred element type from `_infer_list_type` (or None if
            unknown). 'datetime' is treated as 'string' for applicability.

    Returns:
        A list of issue dicts, each with keys: 'level' ('error' | 'warn'),
        'code', 'message', and 'step_index' (position in the pipeline, or None
        for field-level notes). Empty list means the pipeline is well-formed.
    """
    if not pipeline or pipeline == "auto":
        return []

    steps = [s for s in pipeline.split("_") if s]
    issues: list[dict] = []

    # `cur` tracks the element type flowing into each step. datetime is a
    # string subtype for the schemes that accept strings (cat, rle).
    display_type = list_type
    cur = "string" if list_type == "datetime" else list_type

    if cur == "mixed":
        issues.append({
            "level": "warn",
            "code": "mixed_type",
            "message": "This field mixes value types; most schemes need a single "
                       "element type and may fail or barely compress.",
            "step_index": None,
        })
        cur = None
    elif cur in ("empty", None):
        cur = None

    seen_aux: set[str] = set()

    for i, step in enumerate(steps):
        is_last = i == len(steps) - 1

        if step not in _AUTO_TYPE_TRANSITIONS:
            issues.append({
                "level": "error",
                "code": "unknown_scheme",
                "message": f"'{step}' is not a known encoding scheme.",
                "step_index": i,
            })
            cur = None
            continue

        label = _SCHEME_LABELS.get(step, step)
        trans = _AUTO_TYPE_TRANSITIONS[step]

        # aux-emitting steps carry metadata a second pass can't reproduce.
        if step in _AUTO_AUX_EMITTING and step in seen_aux:
            issues.append({
                "level": "error",
                "code": "aux_repeat",
                "message": f"{label} can only appear once in a pipeline — it emits "
                           f"auxiliary metadata that a second pass can't reproduce.",
                "step_index": i,
            })
            cur = None
            continue
        if step in _AUTO_AUX_EMITTING:
            seen_aux.add(step)

        # Type applicability, and whether this step yields a terminal (non-list)
        # output that nothing can follow.
        terminal_output = False
        if cur is not None:
            if cur not in trans:
                got = _TYPE_LABELS.get(display_type if i == 0 else cur, cur)
                issues.append({
                    "level": "error",
                    "code": "type_mismatch",
                    "message": f"{label} expects {_accepted_types_phrase(step)} input, "
                               f"but receives {got} here.",
                    "step_index": i,
                })
                cur = None
            else:
                out = trans[cur]
                if out == "_terminal":
                    terminal_output = True
                    cur = None
                else:
                    cur = out
        else:
            terminal_output = step in _AUTO_TERMINAL

        if terminal_output and not is_last:
            n_after = len(steps) - 1 - i
            issues.append({
                "level": "error",
                "code": "not_terminal_last",
                "message": f"{label} produces a packed, non-list output, so it must be "
                           f"the final step — the {n_after} step"
                           f"{'s' if n_after != 1 else ''} after it can't run.",
                "step_index": i,
            })

    return issues


def _auto_can_apply(step: str, values: list, used_aux: frozenset) -> bool:
    """Decide whether `step` is applicable to `values` given already-used aux-emitting steps."""
    if step in _AUTO_AUX_EMITTING and step in used_aux:
        return False

    t = _infer_list_type(values)
    if t in ("empty", "mixed"):
        return False

    if step == "bm":
        return t == "binary" and len(values) <= 16383
    if step in ("bp", "nbp"):
        return t in ("binary", "int")
    if step == "cat":
        return t == "string"
    if step in ("del", "stl", "quant"):
        return t in ("binary", "int", "float")
    if step in ("tbqm", "tbqp"):
        return t == "float" and len(values) >= 3
    if step == "rle":
        return True
    return False


def _auto_measure(encoded_value, scheme: str, aux: dict) -> int:
    """Size of an encoded result, matching the wire-format measurement in `encode_feature`."""
    entry = [encoded_value, scheme]
    if aux:
        entry.append(aux)
    return get_json_byte_size(entry)


def auto_encode(values, max_depth: int = _AUTO_MAX_DEPTH, lossy: bool = True) -> tuple[Any, str, dict]:
    """Find the best encoding pipeline for `values` by graph search.

    Explores combinations of encoding steps, tracking the smallest output found.
    Aux-emitting steps (cat, del, quant, stl) cannot repeat in a path; terminal
    steps (bm, bp, nbp) cannot have children. Pruning is structural only — the
    search continues through transient size increases (e.g., `cat` alone is
    larger than its input, but `cat_rle_bp` may be much smaller).

    Args:
        values: Original input values.
        max_depth: Maximum pipeline length.
        lossy: If True (default), include lossy schemes (quant, tbqm, tbqp) as candidates.

    Returns:
        Tuple of (encoded_value, scheme_string, auxiliary_info). When no path
        beats the original size, returns the original values with empty
        scheme and aux.
    """
    values = _ensure_list(values)
    original_size = get_json_byte_size([values])

    allowed = set(_AUTO_DEFAULT_CANDIDATES)
    if lossy:
        allowed.update(_AUTO_LOSSY_CANDIDATES)

    root_type = _infer_list_type(values)
    if root_type in ("empty", "mixed"):
        return values, "", {}

    best = {"value": values, "scheme": "", "aux": {}, "size": original_size}

    def dfs(current_values, current_type: str, scheme_parts: list, aux_info: dict, used_aux: frozenset, depth: int):
        if depth >= max_depth:
            return
        candidates = _AUTO_ROOT_SEEDS.get(current_type, ()) if depth == 0 else _AUTO_VALID_FOR_TYPE.get(current_type, ())
        for step in candidates:
            if step not in allowed:
                continue
            if step in used_aux:
                continue
            # tbqm/tbqp are only useful as the first transform on the raw float
            # input: after other steps the dimension is unpredictable, codebooks
            # are uncached, and the computation cost is very high.
            if step in ("tbqm", "tbqp") and depth > 0:
                continue
            if step == "bm" and len(current_values) > 16383:
                continue
            try:
                new_value, new_aux = ENCODING_SCHEMES[step].encode(current_values)
            except Exception:
                continue

            new_aux_info = {**aux_info, **new_aux}
            new_scheme_parts = scheme_parts + [step]
            new_scheme = "_".join(new_scheme_parts)
            new_size = _auto_measure(new_value, new_scheme, new_aux_info)

            if new_size < best["size"]:
                best["value"] = new_value
                best["scheme"] = new_scheme
                best["aux"] = dict(new_aux_info)
                best["size"] = new_size

            output_type = _AUTO_TYPE_TRANSITIONS[step][current_type]
            if output_type == "_terminal" or not new_value:
                continue

            new_used = used_aux | {step} if step in _AUTO_AUX_EMITTING else used_aux
            dfs(new_value, output_type, new_scheme_parts, new_aux_info, new_used, depth + 1)

    dfs(values, root_type, [], {}, frozenset(), 0)
    return best["value"], best["scheme"], best["aux"]
