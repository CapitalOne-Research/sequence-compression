#!/usr/bin/env python3
"""
Compression Playground — local HTTP server.

A thin shell that hands files to the existing
`c1.aiml.compression.encoding.feature_encode.encode_feature_df` and serves
results to the editorial UI under `web/`. There is no encoding logic here —
this is purely transport.

Run:
    python -m web.server [port]      (from repo root, with venv activated)
    python web/server.py [port]
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import os
import time
from collections import OrderedDict
from pathlib import Path

import pandas as pd
import tornado.ioloop
import tornado.web

from c1.aiml.compression.encoding.feature_encode import encode_feature_df
from c1.aiml.compression.encoding.auto_encode import _infer_list_type, auto_encode, validate_pipeline
from c1.aiml.compression.decoding.schemes.quant_decoding import decode as quant_decode
from c1.aiml.compression.decoding.schemes.tbqm_decoding import decode as tbqm_decode
from c1.aiml.compression.decoding.schemes.tbqp_decoding import decode as tbqp_decode
from c1.aiml.compression.utils.lookup import DECODE_PARAMS, DECODING_SCHEMES, ENCODING_SCHEMES
from c1.aiml.compression.utils.metrics import quantization_loss
from c1.aiml.compression.utils.sizing import get_json_byte_size, _ensure_list

WEB_DIR = Path(__file__).resolve().parent
LOG = logging.getLogger("playground")

# Upload cap. Mirrored on the frontend in `app.js` (MAX_UPLOAD).
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# ─── DataFrame cache ─────────────────────────────────────────────────────
# Keyed by md5(file_bytes). Bounded; oldest evicted on overflow. This means a
# user uploading the same file twice (inspect + encode) only pays the parse
# cost once.

_DF_CACHE: "OrderedDict[str, tuple[str, pd.DataFrame]]" = OrderedDict()
_DF_CACHE_MAX = 4


def _file_hash(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


import ast
import re

# Tokeniser for numpy-repr lists like "['A' 'B']" or "[1 2 3]" — single-quoted
# strings, double-quoted strings, or whitespace-separated bare tokens.
_NUMPY_REPR_TOKEN = re.compile(r"'([^']*)'|\"([^\"]*)\"|([^\s,]+)")


def _coerce_token(tok: str):
    """Numeric coercion for bare numpy tokens; falls back to the string."""
    try:
        if '.' in tok or 'e' in tok.lower() or 'inf' in tok.lower() or 'nan' in tok.lower():
            return float(tok)
        return int(tok)
    except (ValueError, TypeError):
        return tok


def _has_top_level_comma(inner: str) -> bool:
    """True if `inner` contains a comma outside any string or nested bracket."""
    in_s = in_d = False
    depth = 0
    i = 0
    while i < len(inner):
        c = inner[i]
        if c == '\\' and i + 1 < len(inner):
            i += 2
            continue
        if c == "'" and not in_d:
            in_s = not in_s
        elif c == '"' and not in_s:
            in_d = not in_d
        elif not in_s and not in_d:
            if c in '[{(':
                depth += 1
            elif c in ']})':
                depth -= 1
            elif c == ',' and depth == 0:
                return True
        i += 1
    return False


def _maybe_parse_list(v):
    """Parse list-shaped cell strings: JSON, numpy repr, or Python repr.

    CSVs from pandas/numpy commonly emit cells like ``"['A' 'B' 'C']"`` or
    ``"[1 2 3]"`` — single quotes, whitespace-separated, no commas. We try
    progressively looser parsers so list-mode inspection works regardless of
    the dump format.

    Order matters: numpy repr is tried before ``ast.literal_eval`` because
    Python silently concatenates adjacent string literals
    (``['A' 'B']`` → ``['AB']``), which would corrupt numpy-style cells.
    """
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not (s.startswith('[') and s.endswith(']')):
        return v

    # 1) strict JSON — fastest, handles nested cleanly
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    inner = s[1:-1].strip()
    if not inner:
        return []

    # 2) numpy repr — no top-level commas, whitespace-separated tokens.
    if not _has_top_level_comma(inner):
        items = []
        for m in _NUMPY_REPR_TOKEN.finditer(inner):
            if m.group(1) is not None:
                items.append(m.group(1))
            elif m.group(2) is not None:
                items.append(m.group(2))
            elif m.group(3) is not None:
                items.append(_coerce_token(m.group(3)))
        if items:
            return items

    # 3) Python repr — handles single quotes, comma-separated, nested
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            return parsed
    except (ValueError, SyntaxError):
        pass

    return v


def _parse_file(content: bytes, filename: str) -> pd.DataFrame:
    bio = io.BytesIO(content)
    is_parquet = filename.lower().endswith('.parquet') or content[:4] == b'PAR1'
    df = pd.read_parquet(bio) if is_parquet else pd.read_csv(bio)
    if is_parquet:
        # Parquet can store array columns as numpy.ndarray per cell; convert to
        # plain Python lists so the rest of the pipeline (hashing, JSON, etc.) works.
        import numpy as np
        for col in df.columns:
            sample = df[col].dropna().head(1)
            if len(sample) and isinstance(sample.iloc[0], np.ndarray):
                df[col] = df[col].apply(lambda v: v.tolist() if isinstance(v, np.ndarray) else v)
    else:
        # CSV: cells holding list-shaped strings (JSON / Python / numpy repr) are
        # parsed so list-mode shows correctly. We sample the first non-null cell
        # of every column rather than gating on dtype — pandas 3.x reports `str`
        # not `object` for inferred string columns.
        for col in df.columns:
            sample = df[col].dropna().head(5)
            if any(isinstance(v, str) and v.strip().startswith('[') for v in sample):
                df[col] = df[col].apply(_maybe_parse_list)
    return df


def _get_df(content: bytes, filename: str) -> tuple[str, pd.DataFrame]:
    h = _file_hash(content)
    if h in _DF_CACHE:
        _DF_CACHE.move_to_end(h)
        return h, _DF_CACHE[h][1]
    df = _parse_file(content, filename)
    _DF_CACHE[h] = (filename, df)
    while len(_DF_CACHE) > _DF_CACHE_MAX:
        _DF_CACHE.popitem(last=False)
    return h, df


def _wrap_scalars(df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """Wrap scalar cells of columns in `schema` into single-element lists.

    `encode_feature_df` expects list-valued features; scalar columns crash the
    iterating encoders (cat/rle/etc.). Wrapping each scalar cell as `[value]`
    matches the `[value]` wire-format semantics produced by `encode_feature`
    when no encoding is applied, and matches the size accounting used in
    `_profile_column`.
    """
    if not schema:
        return df
    out = df
    cloned = False
    for col in df.columns:
        if col not in schema:
            continue
        head = df[col].head(50).tolist()
        if any(isinstance(v, list) for v in head):
            continue  # already a list column
        if not cloned:
            out = df.copy()
            cloned = True
        out[col] = df[col].apply(
            lambda v: [v] if (v is not None and not (isinstance(v, float) and pd.isna(v))) else []
        )
    return out


# ─── inspection ──────────────────────────────────────────────────────────

def _hashable(v):
    if isinstance(v, list):
        return tuple(_hashable(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, _hashable(x)) for k, x in v.items()))
    return v


def _format_sample(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "∅"
    if isinstance(v, list):
        inner = ",".join(_format_sample(x) for x in v[:3])
        return f"[{inner}{'…' if len(v) > 3 else ''}]"
    if isinstance(v, str):
        s = v if len(v) <= 22 else v[:22] + "…"
        return f'"{s}"'
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def _profile_column(name: str, series: pd.Series) -> dict:
    head = series.head(min(len(series), 200)).tolist()

    array_count = sum(1 for v in head if isinstance(v, list))
    is_list = array_count > 0 and array_count / max(1, len(head)) >= 0.5

    samples: list[str] = []
    for v in head[:8]:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        samples.append(_format_sample(v))
        if len(samples) >= 4:
            break

    if is_list:
        flat: list = []
        for v in series:
            if isinstance(v, list):
                flat.extend(v[:200])  # cap per-row contribution
            if len(flat) >= 5000:
                break
        inferred_type = _infer_list_type(flat[:2000])
        cardinality = len({_hashable(x) for x in flat[:10000]})
        non_null = int(sum(1 for v in series if isinstance(v, list)))
        total_elements = int(sum(len(v) for v in series if isinstance(v, list)))
    else:
        non_null_values = [v for v in series if v is not None and not (isinstance(v, float) and pd.isna(v))]
        inferred_type = _infer_list_type(non_null_values[:2000])
        cardinality = len({_hashable(x) for x in non_null_values[:10000]})
        non_null = len(non_null_values)
        total_elements = non_null

    # Original size — match the wire-format accounting in encode_feature: every
    # row contributes `get_json_byte_size([row_value])` (the unencoded entry).
    original_size = 0
    for v in series:
        cell = v if isinstance(v, list) else ([v] if (v is not None and not (isinstance(v, float) and pd.isna(v))) else [])
        original_size += get_json_byte_size([cell])

    avg_seq_len = round(total_elements / non_null, 1) if non_null else 0

    return {
        "name": name,
        "type": inferred_type,
        "is_list": is_list,
        "cardinality": cardinality,
        "avg_seq_len": avg_seq_len,
        "non_null": non_null,
        "total_elements": total_elements,
        "samples": samples,
        "original_size": original_size,
    }


# ─── recommendation heuristic ────────────────────────────────────────────
# Mirrors the candidate-list pattern used in encoding_schemes.md.

def _recommend(profile: dict) -> str | None:
    t = profile["type"]
    denom = profile.get("total_elements") or profile["non_null"] or 1
    ratio = profile["cardinality"] / max(1, denom)

    if t == "binary":
        return "bm"
    if t == "float":
        return "quant_bp"
    if t == "string":
        if ratio < 0.1:
            return "cat_rle_bp"
        if ratio < 0.5:
            return "cat_bp"
        return "cat"
    if t == "int":
        # Integers are usually one of three shapes:
        #   - very low cardinality / repeated values → rle_bp captures runs
        #   - ordered / smooth (timestamps, counters)  → del_bp (small deltas)
        #   - sparse with one dominant value           → handled by `auto`
        # We default to del_bp because most int sequences worth compressing
        # are ordered. Treating mid-cardinality ints as dictionary-encodable
        # produced `cat_rle_bp` recommendations on timestamp columns, which
        # is strictly worse than del_bp for monotonic data.
        if ratio < 0.05:
            return "rle_bp"
        return "del_bp"
    return None


# ─── tornado handlers ────────────────────────────────────────────────────

class _JsonHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def write_error(self, status_code: int, **kwargs):
        exc_info = kwargs.get("exc_info")
        message = "internal error"
        if exc_info:
            message = f"{exc_info[0].__name__}: {exc_info[1]}"
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.finish(json.dumps({"error": message}))

    def reject_oversize(self, info: dict) -> bool:
        """Return True (and emit a 413) if the uploaded file exceeds the cap."""
        body = info.get("body", b"")
        if len(body) > MAX_UPLOAD_BYTES:
            self.set_status(413)
            self.finish(json.dumps({
                "error": (
                    f"file too large: {len(body):,} bytes "
                    f"(max {MAX_UPLOAD_BYTES:,} = 10 MB)"
                ),
            }))
            return True
        return False


class InspectHandler(_JsonHandler):
    def post(self):
        if "file" not in self.request.files:
            self.set_status(400)
            return self.finish(json.dumps({"error": "no file uploaded"}))

        info = self.request.files["file"][0]
        if self.reject_oversize(info):
            return
        try:
            file_id, df = _get_df(info["body"], info["filename"])
        except Exception as e:
            self.set_status(400)
            return self.finish(json.dumps({"error": f"could not parse file: {e}"}))

        cols = [_profile_column(c, df[c]) for c in df.columns]
        for c in cols:
            c["recommended"] = _recommend(c)

        self.finish(json.dumps({
            "id": file_id,
            "filename": info["filename"],
            "row_count": len(df),
            "columns": cols,
            "total_size": sum(c["original_size"] for c in cols),
        }))


class EncodeHandler(_JsonHandler):
    def post(self):
        if "file" not in self.request.files:
            self.set_status(400)
            return self.finish(json.dumps({"error": "no file uploaded"}))

        info = self.request.files["file"][0]
        if self.reject_oversize(info):
            return
        try:
            file_id, df = _get_df(info["body"], info["filename"])
        except Exception as e:
            self.set_status(400)
            return self.finish(json.dumps({"error": f"could not parse file: {e}"}))

        try:
            schema_raw = self.get_body_argument("schema", "{}")
            raw = json.loads(schema_raw)
            # values may be list-of-candidates; pass through to encode_feature_payload as-is
            schema = {k: v for k, v in raw.items() if v}
        except Exception:
            schema = {}

        lossy_raw = self.get_body_argument("lossy", "true")
        lossy = lossy_raw.lower() not in ("false", "0", "no")

        # encode_feature_df expects list-valued cells; wrap scalar columns in
        # single-element lists so the schemes don't trip on non-iterables.
        # This mirrors the size accounting in `_profile_column` and matches the
        # `[value]` wire-format semantics in `encode_feature`.
        df_for_encoding = _wrap_scalars(df, schema)

        start = time.perf_counter()
        try:
            encoded_df = encode_feature_df(df_for_encoding, schema, drop_originals=True, lossy=lossy)
        except Exception as e:
            self.set_status(500)
            return self.finish(json.dumps({"error": f"encode_feature_df: {type(e).__name__}: {e}"}))
        elapsed_ms = (time.perf_counter() - start) * 1000

        per_column = []
        for col_name in df.columns:
            enc_col = f"{col_name}_enc"
            if enc_col not in encoded_df.columns:
                continue

            head = df[col_name].head(50).tolist()
            array_count = sum(1 for v in head if isinstance(v, list))
            is_list = array_count > 0 and array_count / max(1, len(head)) >= 0.5

            orig_size = 0
            for v in df[col_name]:
                cell = v if isinstance(v, list) else ([v] if (v is not None and not (isinstance(v, float) and pd.isna(v))) else [])
                orig_size += get_json_byte_size([cell])

            enc_size = int(encoded_df[enc_col].map(lambda s: len(s.encode("utf-8"))).sum())

            # Per-row scheme histogram. With `auto`, each row's pipeline is
            # picked independently — they may differ. ``None`` means the
            # encoded payload was no smaller than the original, so the row
            # was retained unencoded (the standard `encode_feature` fallback).
            scheme_hist: dict[str | None, int] = {}
            wire_value = None
            for row_val in encoded_df[enc_col]:
                row_scheme = None
                if isinstance(row_val, str) and row_val:
                    try:
                        parsed = json.loads(row_val)
                        if isinstance(parsed, list) and len(parsed) >= 2:
                            row_scheme = parsed[1]
                    except (json.JSONDecodeError, ValueError):
                        pass
                    if wire_value is None:
                        wire_value = row_val
                scheme_hist[row_scheme] = scheme_hist.get(row_scheme, 0) + 1

            scheme_breakdown = sorted(
                ({"scheme": s, "count": n} for s, n in scheme_hist.items()),
                key=lambda x: -x["count"],
            )
            # Primary scheme = most common non-null; falls back to None if all rows skipped.
            scheme = next((b["scheme"] for b in scheme_breakdown if b["scheme"]), None)
            encoded_rows = sum(b["count"] for b in scheme_breakdown if b["scheme"])
            skipped_rows = sum(b["count"] for b in scheme_breakdown if not b["scheme"])

            # Pull the representative row's full triple [value, scheme, aux] so
            # the UI can show what was actually serialised — the aux dict is
            # part of the stored wire entry, not a separate file artifact.
            wire_aux: dict | None = None
            wire_scheme: str | None = None
            wire_value_only = None
            if isinstance(wire_value, str) and wire_value:
                try:
                    parsed = json.loads(wire_value)
                    if isinstance(parsed, list) and len(parsed) >= 1:
                        wire_value_only = parsed[0]
                    if isinstance(parsed, list) and len(parsed) >= 2:
                        wire_scheme = parsed[1]
                    if isinstance(parsed, list) and len(parsed) >= 3 and isinstance(parsed[2], dict):
                        wire_aux = parsed[2]
                except (json.JSONDecodeError, ValueError):
                    pass

            # Original (uncompressed) row-1 entry: the cell value as it would
            # be stored without any encoding — [cell] for a list cell or [[v]]
            # for a scalar. This is what encode_feature_payload emits when the
            # encoded form is no smaller than the original.
            wire_orig_cell = None
            wire_orig_bytes = 0
            if len(df) > 0:
                raw_cell = df[col_name].iloc[0]
                if isinstance(raw_cell, list):
                    wire_orig_cell = raw_cell
                elif raw_cell is not None and not (isinstance(raw_cell, float) and pd.isna(raw_cell)):
                    wire_orig_cell = [raw_cell]
                else:
                    wire_orig_cell = []
                wire_orig_bytes = get_json_byte_size([wire_orig_cell])

            requested = schema.get(col_name, "")
            if isinstance(requested, list):
                requested = "|".join(requested)

            per_column.append({
                "name": col_name,
                "is_list": is_list,
                "requested": requested,
                "scheme": scheme,
                "scheme_breakdown": scheme_breakdown,
                "encoded_rows": encoded_rows,
                "skipped_rows": skipped_rows,
                "row_count": len(df),
                "orig_size": orig_size,
                "enc_size": enc_size,
                "wire_value": wire_value,
                "wire_scheme": wire_scheme,
                "wire_aux": wire_aux,
                "wire_aux_keys": list(wire_aux.keys()) if wire_aux else [],
                "wire_orig_cell": wire_orig_cell,
                "wire_orig_bytes": wire_orig_bytes,
            })

        self.finish(json.dumps({
            "elapsed_ms": elapsed_ms,
            "row_count": len(df),
            "total_orig": sum(c["orig_size"] for c in per_column),
            "total_enc": sum(c["enc_size"] for c in per_column),
            "per_column": per_column,
        }))


class DefaultDatasetHandler(_JsonHandler):
    """Serve the bundled sample dataset without a file upload.

    Returns the same shape as InspectHandler so the frontend can feed it
    directly into the schema/pipeline flow without any special-casing.
    """

    _SAMPLE_PATH = WEB_DIR / "sample_datasets" / "kuairand_demo.parquet"

    def get(self):
        path = self._SAMPLE_PATH
        if not path.exists():
            self.set_status(404)
            return self.finish(json.dumps({"error": "sample dataset not found"}))
        try:
            content = path.read_bytes()
            file_id, df = _get_df(content, path.name)
        except Exception as e:
            self.set_status(500)
            return self.finish(json.dumps({"error": f"could not load sample dataset: {e}"}))

        cols = [_profile_column(c, df[c]) for c in df.columns]
        for c in cols:
            c["recommended"] = _recommend(c)

        self.finish(json.dumps({
            "id": file_id,
            "filename": path.name,
            "row_count": len(df),
            "columns": cols,
            "total_size": sum(c["original_size"] for c in cols),
            "is_default": True,
        }))


class _NoCacheStatic(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path: str) -> None:
        # Force the browser to revalidate every fetch — UI iterates fast and
        # stale `index.html` against fresh `app.js` produces silent null-element
        # crashes. ``no-store`` is intentionally heavy-handed for local dev.
        self.set_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.set_header("Pragma", "no-cache")
        self.set_header("Expires", "0")


# ─── inspector · per-step inspector ─────────────────────────────────────

_SCHEME_META = {
    "cat":   ("Categorical",      "Map each unique value to a small integer id (most-frequent → 0)."),
    "quant": ("Quantization",     "Map floats onto an 8-bit integer grid (lossy)."),
    "del":   ("Delta",            "Replace each value with the difference from its predecessor."),
    "rle":   ("Run-Length",       "Collapse runs of equal values into [value, count] pairs."),
    "stl":   ("Sentinel",         "Strip outlier values, store their positions separately."),
    "bp":    ("Bit-Pack",         "Pack ints into a base64 bitstream using min bits per value."),
    "bm":    ("Bitmap",           "0/1 sequence packed bit-by-bit into base64."),
    "nbp":   ("Nullmap Bit-Pack", "Sparse → dominant value + nullmap + packed non-dominants."),
    "tbqm":  ("TurboQuant MSE",   "Random-rotation + Lloyd-Max codebook vector quantization (lossy, MSE-optimal)."),
    "tbqp":  ("TurboQuant Prod",  "TurboQuant MSE + QJL residual for unbiased inner-product estimation (lossy)."),
}

_DECODE_DESCRIPTIONS = {
    "cat":   "Look up each integer id in the dictionary (itos = inverse of stoi) to recover the original strings.",
    "quant": "Multiply each uint8 code by the scale (and offset by zero_point) to recover an approximate float. Lossy: small per-value error remains.",
    "del":   "Cumulative-sum the deltas starting from the stored v0 to rebuild the original sequence.",
    "rle":   "Expand each [value, count] pair back into `count` copies of `value`.",
    "stl":   "Splice the stripped sentinel values back into their original positions from snt_ranges.",
    "bp":    "Unpack the base64 bitstream using the header (bit width, length) to recover the integer sequence.",
    "bm":    "Unpack each bit of the base64 bytes back into a 0/1 sequence.",
    "nbp":   "Combine the dominant value, nullmap, and packed non-dominants to rebuild the sparse sequence.",
    "tbqm":  "Unpack codebook indices, look up Lloyd-Max centroids, inverse-rotate, denormalize by stored norm. Lossy: quantization error remains.",
    "tbqp":  "Unpack MSE indices + QJL signs, reconstruct MSE part + QJL correction, combine and denormalize. Lossy: optimized for inner-product fidelity, not MSE.",
}


class StepsHandler(_JsonHandler):
    """Run a pipeline step-by-step over a user-provided sequence and return
    every intermediate state. Used by the inspector page."""

    def post(self):
        try:
            body = json.loads(self.request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            self.set_status(400)
            return self.finish(json.dumps({"error": "body must be json"}))

        values = body.get("values")
        pipeline = body.get("pipeline", "")
        allow_lossy = bool(body.get("lossy", True))

        if values is None:
            self.set_status(400)
            return self.finish(json.dumps({"error": "missing 'values'"}))
        if not isinstance(values, list):
            values = _ensure_list(values)
            if not isinstance(values, list):
                self.set_status(400)
                return self.finish(json.dumps({"error": "'values' must be a list"}))
        if not pipeline:
            self.set_status(400)
            return self.finish(json.dumps({"error": "missing 'pipeline'"}))

        # auto: resolve to a concrete pipeline first, then run it step by step
        # so the user sees the discovered chain rather than a black box.
        resolved_pipeline = pipeline
        auto_origin = None
        if pipeline == "auto":
            _, discovered_scheme, _ = auto_encode(values, lossy=allow_lossy)
            if not discovered_scheme:
                return self.finish(json.dumps({
                    "pipeline": pipeline,
                    "resolved_pipeline": "",
                    "auto_origin": "auto",
                    "steps": [{
                        "step": "input",
                        "name": "Input",
                        "description": "Auto found no pipeline that beat the original size — kept unencoded.",
                        "input": None,
                        "output": values,
                        "aux": {},
                        "cumulative_aux": {},
                        "byte_size": get_json_byte_size([values]),
                        "pipeline_so_far": "",
                    }],
                }))
            resolved_pipeline = discovered_scheme
            auto_origin = "auto"

        steps = resolved_pipeline.split("_")
        history = [{
            "step": "input",
            "name": "Input",
            "description": "The original sequence — measured as the wire-format entry [values].",
            "input": None,
            "output": values,
            "aux": {},
            "cumulative_aux": {},
            "byte_size": get_json_byte_size([values]),
            "pipeline_so_far": "",
        }]

        current = values
        cumulative_aux: dict = {}

        for i, step_name in enumerate(steps):
            scheme = ENCODING_SCHEMES.get(step_name)
            if scheme is None:
                self.set_status(400)
                return self.finish(json.dumps({"error": f"unknown scheme: {step_name}"}))

            try:
                new_value, new_aux = scheme.encode(_ensure_list(current))
            except Exception as e:
                self.set_status(400)
                return self.finish(json.dumps({
                    "error": f"step '{step_name}' failed: {type(e).__name__}: {e}",
                    "pipeline": pipeline,
                    "resolved_pipeline": resolved_pipeline,
                    "failed_at": i,
                    "steps": history,
                }))

            cumulative_aux = {**cumulative_aux, **(new_aux or {})}
            pipeline_so_far = "_".join(steps[: i + 1])

            entry = [new_value, pipeline_so_far]
            if cumulative_aux:
                entry.append(cumulative_aux)
            byte_size = get_json_byte_size(entry)

            display_name, description = _SCHEME_META.get(
                step_name, (step_name, ""))

            history.append({
                "step": step_name,
                "name": display_name,
                "description": description,
                "input": current,
                "output": new_value,
                "aux": new_aux or {},
                "cumulative_aux": cumulative_aux,
                "byte_size": byte_size,
                "pipeline_so_far": pipeline_so_far,
            })

            # quant/tbqm/tbqp are lossy steps — round-trip the output through
            # the corresponding decoder to measure precision loss vs the floats
            # this step received. Metrics are attached to the matching DECODE
            # step below (lossy reconstruction is fundamentally a decode-time
            # concern).
            if step_name == "quant":
                try:
                    reconstructed = quant_decode(
                        new_value,
                        q_scale=float(new_aux.get("q_scale", 1.0) or 0.0),
                        q_zp=float(new_aux.get("q_zp", 0.0) or 0.0),
                        q_bits=int(new_aux.get("q_bits", 8) or 8),
                        q_sym=int(new_aux.get("q_sym", 0) or 0),
                    )
                    loss = quantization_loss(_ensure_list(current), reconstructed)
                    if loss.get("snr_db") == float("inf"):
                        loss["snr_db"] = None
                    history[-1]["_loss_metrics"] = loss
                    history[-1]["_reconstructed_sample"] = reconstructed[:24]
                    history[-1]["_original_sample"] = _ensure_list(current)[:24]
                except Exception:
                    pass
            elif step_name in ("tbqm", "tbqp"):
                try:
                    decode_fn = tbqm_decode if step_name == "tbqm" else tbqp_decode
                    reconstructed = decode_fn(
                        new_value,
                        tq_dim=int(new_aux.get("tq_dim", 0) or 0),
                        tq_bits=int(new_aux.get("tq_bits", 4) or 4),
                        tq_seed=int(new_aux.get("tq_seed", 42) or 42),
                        tq_norm=float(new_aux.get("tq_norm", 1.0) or 1.0),
                        **({
                            "tq_rnorm": new_aux.get("tq_rnorm"),
                            "tq_qseed": new_aux.get("tq_qseed"),
                        } if step_name == "tbqp" else {}),
                    )
                    loss = quantization_loss(_ensure_list(current), reconstructed)
                    if loss.get("snr_db") == float("inf"):
                        loss["snr_db"] = None
                    history[-1]["_loss_metrics"] = loss
                    history[-1]["_reconstructed_sample"] = reconstructed[:24]
                    history[-1]["_original_sample"] = _ensure_list(current)[:24]
                except Exception:
                    pass

            current = new_value

        # ── decode walk-back ───────────────────────────────────────
        # Mirror `decode_feature`: walk the pipeline in reverse, calling
        # each scheme's decode with the aux keys it consumes (drawn from
        # the cumulative aux as that's what the wire format actually
        # carries). Record every intermediate state for visualisation.
        decode_history: list = []
        if resolved_pipeline:
            decode_history.append({
                "step": "encoded",
                "name": "Encoded",
                "description": "The wire-format value as it would be stored. Decoding walks the pipeline in reverse.",
                "input": None,
                "output": current,
                "aux_used": {},
                "byte_size": get_json_byte_size([current]),
            })

            decode_current = current
            decode_steps_list = steps[::-1]
            for j, step_name in enumerate(decode_steps_list):
                module = DECODING_SCHEMES.get(step_name)
                if module is None:
                    continue
                params = DECODE_PARAMS.get(step_name, [])
                kwargs = {k: cumulative_aux[k] for k in params if k in cumulative_aux}
                try:
                    decoded_value = module.decode(_ensure_list(decode_current), **kwargs)
                except Exception as e:
                    decode_history.append({
                        "step": step_name,
                        "name": _SCHEME_META.get(step_name, (step_name, ""))[0],
                        "description": _DECODE_DESCRIPTIONS.get(step_name, ""),
                        "error": f"{type(e).__name__}: {e}",
                        "input": decode_current,
                        "aux_used": kwargs,
                    })
                    break

                display_name, _ = _SCHEME_META.get(step_name, (step_name, ""))
                decode_entry = {
                    "step": step_name,
                    "name": display_name,
                    "description": _DECODE_DESCRIPTIONS.get(step_name, ""),
                    "input": decode_current,
                    "output": decoded_value,
                    "aux_used": kwargs,
                    "byte_size": get_json_byte_size([decoded_value]),
                }

                # Migrate lossy-reconstruction metrics from the matching
                # encode entry onto this decode entry. Encode step index in
                # `history` is `len(steps) - j` (history[0] is the original
                # input placeholder, so encode steps live at indices 1..N).
                enc_idx = len(steps) - j
                if 0 < enc_idx < len(history):
                    enc_entry = history[enc_idx]
                    if "_loss_metrics" in enc_entry:
                        decode_entry["loss_metrics"] = enc_entry.pop("_loss_metrics")
                        decode_entry["reconstructed_sample"] = enc_entry.pop("_reconstructed_sample", [])
                        decode_entry["original_sample"] = enc_entry.pop("_original_sample", [])

                decode_history.append(decode_entry)
                decode_current = decoded_value

        self.finish(json.dumps({
            "pipeline": pipeline,
            "resolved_pipeline": resolved_pipeline,
            "auto_origin": auto_origin,
            "steps": history,
            "decode_steps": decode_history,
        }))


class HealthHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.finish('{"status":"ok"}')


class ValidateHandler(_JsonHandler):
    """Flag improper pipelines for a given data type without encoding.

    Powers the composer/inspector warnings. Each check supplies a `pipeline`
    plus either a pre-inferred `type` (the composer already has it from
    /api/inspect) or the raw `values` (the inspector lets the server infer via
    `_infer_list_type`, keeping type classification in one place). Validation
    itself is `validate_pipeline` — the same transition table the encoder uses.
    """

    def post(self):
        try:
            body = json.loads(self.request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            self.set_status(400)
            return self.finish(json.dumps({"error": "body must be json"}))

        checks = body.get("checks")
        if not isinstance(checks, list):
            self.set_status(400)
            return self.finish(json.dumps({"error": "missing 'checks' list"}))

        results = []
        for chk in checks:
            if not isinstance(chk, dict):
                continue
            pipeline = chk.get("pipeline") or ""
            list_type = chk.get("type")
            if list_type is None:
                vals = chk.get("values")
                if isinstance(vals, list):
                    list_type = _infer_list_type(vals[:2000])
            results.append({
                "key": chk.get("key"),
                "pipeline": pipeline,
                "type": list_type,
                "warnings": validate_pipeline(pipeline, list_type),
            })

        self.finish(json.dumps({"results": results}))


def make_app() -> tornado.web.Application:
    # max_buffer_size needs a little headroom over MAX_UPLOAD_BYTES for multipart
    # envelope, headers, schema field, etc. Tornado rejects with a connection
    # close before our handlers run if this is exceeded.
    return tornado.web.Application([
        (r"/api/health", HealthHandler),
        (r"/api/inspect", InspectHandler),
        (r"/api/encode", EncodeHandler),
        (r"/api/steps", StepsHandler),
        (r"/api/validate", ValidateHandler),
        (r"/api/default-dataset", DefaultDatasetHandler),
        (r"/(.*)", _NoCacheStatic, {"path": str(WEB_DIR), "default_filename": "index.html"}),
    ], max_buffer_size=MAX_UPLOAD_BYTES + 256 * 1024)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8888))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = make_app()
    app.listen(port, address="0.0.0.0")
    LOG.info("compression playground · http://localhost:%d", port)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
