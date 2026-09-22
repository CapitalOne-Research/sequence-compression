"""The wire-format container shared by every seqpack encoding path.

Each feature encodes to a variable-arity list: ``[value]``, ``[value, scheme]``,
or ``[value, scheme, aux]``. Trailing elements are dropped when falsy as a
deliberate byte-saving measure, and this shape -- not a dict or tuple -- is
what every "does this actually compress?" size comparison measures. See
``seqpack/encoding_schemes.md``.

`EncodedEntry` centralizes the construction/parsing/measurement of this
format so the rule lives in one place instead of being hand-rolled at each
call site. It is a pure refactor: `to_wire()` returns a `list` (never a
tuple), since `sizing._convert_keys_to_native` only recurses into `list` --
a tuple would skip numpy-key normalization there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeAlias, TypedDict

# What a scheme's encode() emits: a numeric/string list, or base64 str (bm/bp/nbp).
SchemeValue: TypeAlias = "list[int] | list[float] | list[str] | str"

# Auxiliary decode metadata. dict[str, Any], not a TypedDict: `decode_feature`
# indexes it by a non-literal `str` key (see feature_decode.py), and aux dicts
# from different pipeline steps are merged flat, so no fixed shape applies at
# this boundary. Per-scheme TypedDicts exist below for use *inside* scheme
# modules, where the keys are literals and mypy can actually check them.
AuxInfo: TypeAlias = "dict[str, Any]"

# Underscore-joined pipeline, e.g. "cat_rle_bp". "" or None means pass-through.
SchemeName: TypeAlias = "str | None"


class CatAux(TypedDict):
    stoi: dict[str, int]


class DeltaAux(TypedDict):
    v0: int | float


class QuantAux(TypedDict):
    q_scale: float
    q_zp: float
    q_bits: int
    q_sym: int


class StlAux(TypedDict, total=False):
    # The encoder emits ONE of these two shapes, never both:
    #   - no sentinels found: {snt_pos: [], length}
    #   - sentinels found:    {snt_ranges: {...}, length}
    snt_pos: list[Any]
    snt_ranges: dict[str, list[list[int]]]
    length: int


class TbqmAux(TypedDict):
    tq_dim: int
    tq_bits: int
    tq_seed: int
    tq_norm: float


class TbqpAux(TbqmAux):
    tq_rnorm: float
    tq_qseed: int
    tq_signs: str


class EmptyAux(TypedDict):
    pass


# Registry mirroring seqpack.utils.lookup.DECODE_PARAMS: the keys of each
# TypedDict below must exactly match that scheme's decode() parameter names,
# since decode_feature dispatches kwargs by name. See
# tests/test_wire_golden.py::test_aux_schemas_match_decode_params.
AUX_SCHEMAS: dict[str, type] = {
    "bm": EmptyAux,
    "bp": EmptyAux,
    "nbp": EmptyAux,
    "rle": EmptyAux,
    "cat": CatAux,
    "del": DeltaAux,
    "quant": QuantAux,
    "stl": StlAux,
    "tbqm": TbqmAux,
    "tbqp": TbqpAux,
}


class EncoderModule(Protocol):
    """Structural shape of a `seqpack.encoding.schemes.*` module.

    Not statically verified: `lookup.py` builds `ENCODING_SCHEMES` via
    `importlib.import_module`, which mypy types as `ModuleType` -- a `cast`
    at that call site is what lets dispatch sites see this shape instead of
    `Any`. This is a trusted boundary, not one mypy checks against the
    dynamically imported modules themselves.
    """

    def encode(self, values: Any, /, **options: Any) -> tuple[SchemeValue, AuxInfo]: ...


class DecoderModule(Protocol):
    """Structural shape of a `seqpack.decoding.schemes.*` module. See `EncoderModule`."""

    def decode(self, value: Any, /, **aux: Any) -> list[Any]: ...


@dataclass(frozen=True, slots=True)
class EncodedEntry:
    """One feature's wire entry: [value], [value, scheme], or [value, scheme, aux]."""

    value: Any
    scheme: SchemeName = ""
    aux: AuxInfo = field(default_factory=dict)

    def to_wire(self) -> list[Any]:
        """Build the variable-arity wire list, dropping falsy trailing elements."""
        entry: list[Any] = [self.value]
        if self.scheme:
            entry.append(self.scheme)
            if self.aux:
                entry.append(self.aux)
        return entry

    @classmethod
    def from_wire(cls, entry: list[Any]) -> EncodedEntry:
        """Parse a variable-arity wire list back into an EncodedEntry."""
        return cls(
            entry[0],
            entry[1] if len(entry) > 1 else "",
            entry[2] if len(entry) > 2 else {},
        )

    def byte_size(self) -> int:
        """Compact-JSON byte size of this entry, matching the wire measurement."""
        from seqpack.utils.sizing import get_json_byte_size

        return get_json_byte_size(self.to_wire())
