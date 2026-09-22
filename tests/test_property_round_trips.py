"""Property-based round-trip tests using Hypothesis.

Guarded by pytest.importorskip so the suite stays green without the `dev`
extra installed. These generate many more inputs per scheme than the
hand-picked examples in the per-scheme test files, and are the class of
test that would have caught the delta/stl float-handling bugs immediately
(both were reachable only on float, not int, input).
"""

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

from seqpack.decoding.schemes.bm_decoding import decode as bm_decode
from seqpack.decoding.schemes.bp_decoding import decode as bp_decode
from seqpack.decoding.schemes.cat_decoding import decode as cat_decode
from seqpack.decoding.schemes.delta_decoding import decode as delta_decode
from seqpack.decoding.schemes.nbp_decoding import decode as nbp_decode
from seqpack.decoding.schemes.quant_decoding import decode as quant_decode
from seqpack.decoding.schemes.rle_decoding import decode as rle_decode
from seqpack.encoding.schemes.bm_encoding import encode as bm_encode
from seqpack.encoding.schemes.bp_encoding import encode as bp_encode
from seqpack.encoding.schemes.cat_encoding import encode as cat_encode
from seqpack.encoding.schemes.delta_encoding import encode as delta_encode
from seqpack.encoding.schemes.nbp_encoding import encode as nbp_encode
from seqpack.encoding.schemes.quant_encoding import encode as quant_encode
from seqpack.encoding.schemes.rle_encoding import encode as rle_encode

_settings = settings(max_examples=100, deadline=None)

int_lists = st.lists(st.integers(min_value=-(10**9), max_value=10**9), max_size=200)
binary_lists = st.lists(st.integers(min_value=0, max_value=1), max_size=200)
float_lists = st.lists(
    st.floats(allow_nan=False, allow_infinity=False, width=32, min_value=-1e6, max_value=1e6),
    max_size=200,
)
string_lists = st.lists(st.text(max_size=10), max_size=100)


@given(binary_lists)
@_settings
def test_bm_round_trip_property(values):
    encoded, aux = bm_encode(values)
    assert bm_decode(encoded, **aux) == values


@given(int_lists)
@_settings
def test_bp_round_trip_property(values):
    encoded, aux = bp_encode(values)
    assert bp_decode(encoded, **aux) == values


@given(int_lists)
@_settings
def test_nbp_round_trip_property(values):
    encoded, aux = nbp_encode(values)
    assert nbp_decode(encoded, **aux) == values


@given(int_lists)
@_settings
def test_rle_round_trip_property(values):
    encoded, aux = rle_encode(values)
    assert rle_decode(encoded, **aux) == values


@given(string_lists)
@_settings
def test_cat_round_trip_property(values):
    encoded, aux = cat_encode(values)
    assert cat_decode(encoded, aux["stoi"]) == values


@given(int_lists)
@_settings
def test_delta_round_trip_property_ints_are_exact(values):
    encoded, aux = delta_encode(values)
    assert delta_decode(encoded, **aux) == values


@given(float_lists)
@_settings
def test_delta_round_trip_property_floats_within_float_precision(values):
    # Regression coverage for the float-corruption bug (previously this
    # silently truncated to int, e.g. [1.5, 2.0] -> [1, 1]). Exact equality
    # is not guaranteed for floats: v0 + (v1 - v0) is not always bit-exact
    # with v1 under IEEE 754, independent of this implementation. We assert
    # reconstruction to a small relative tolerance instead.
    encoded, aux = delta_encode(values)
    decoded = delta_decode(encoded, **aux)
    assert len(decoded) == len(values)
    for original, reconstructed in zip(values, decoded):
        assert reconstructed == pytest.approx(original, rel=1e-9, abs=1e-6)


@given(float_lists, st.integers(min_value=1, max_value=16))
@_settings
def test_quant_round_trip_within_scale_tolerance(values, num_bits):
    if not values:
        return
    encoded, aux = quant_encode(values, num_bits=num_bits)
    decoded = quant_decode(encoded, **aux)
    tolerance = aux["q_scale"] or 1e-9
    assert max(abs(a - b) for a, b in zip(values, decoded)) <= tolerance + 1e-6
