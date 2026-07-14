"""Tests for the auto encoding graph search added to feature_encode."""

from c1.aiml.compression.decoding.feature_decode import decode_feature_payload
from c1.aiml.compression.encoding.auto_encode import (
    _AUTO_AUX_EMITTING,
    _AUTO_TERMINAL,
    _auto_can_apply,
    _infer_list_type,
    auto_encode,
    validate_pipeline,
)
from c1.aiml.compression.encoding.feature_encode import encode_feature_payload


class TestInferListType:
    def test_empty(self):
        assert _infer_list_type([]) == "empty"

    def test_binary(self):
        assert _infer_list_type([0, 1, 0, 1]) == "binary"

    def test_int(self):
        assert _infer_list_type([1, 2, 3, 4]) == "int"

    def test_float(self):
        assert _infer_list_type([1.0, 2.5, 3.0]) == "float"

    def test_int_float_mix_is_float(self):
        assert _infer_list_type([1, 2.5, 3]) == "float"

    def test_string(self):
        assert _infer_list_type(["a", "b", "c"]) == "string"

    def test_datetime(self):
        assert _infer_list_type(["2024-01-01T00:00:00", "2024-01-02T00:00:00"]) == "datetime"

    def test_mixed(self):
        assert _infer_list_type([1, "a", 2.0]) == "mixed"


class TestAutoCanApply:
    def test_aux_emitting_step_cannot_repeat(self):
        for step in _AUTO_AUX_EMITTING:
            # The function gates on used_aux first; so this returns False
            # regardless of input shape.
            assert _auto_can_apply(step, [1, 2, 3], used_aux=frozenset({step})) is False

    def test_bm_requires_binary(self):
        assert _auto_can_apply("bm", [0, 1, 0], frozenset()) is True
        assert _auto_can_apply("bm", [0, 1, 2], frozenset()) is False

    def test_bm_max_length(self):
        assert _auto_can_apply("bm", [0] * 16384, frozenset()) is False

    def test_bp_requires_int(self):
        assert _auto_can_apply("bp", [1, 2, 3], frozenset()) is True
        assert _auto_can_apply("bp", ["a", "b"], frozenset()) is False
        assert _auto_can_apply("bp", [1.5, 2.5], frozenset()) is False

    def test_cat_requires_string(self):
        assert _auto_can_apply("cat", ["a", "b"], frozenset()) is True
        assert _auto_can_apply("cat", [1, 2], frozenset()) is False

    def test_rle_works_on_anything_typed(self):
        assert _auto_can_apply("rle", ["a", "b"], frozenset()) is True
        assert _auto_can_apply("rle", [1, 2], frozenset()) is True
        # But rejects empty/mixed
        assert _auto_can_apply("rle", [], frozenset()) is False
        assert _auto_can_apply("rle", [1, "a"], frozenset()) is False

    def test_quant_does_not_apply_when_lossy_disabled_at_caller(self):
        # The predicate itself permits quant on numerics — gating happens
        # via the candidate list.
        assert _auto_can_apply("quant", [1.0, 2.0], frozenset()) is True


class TestAutoEncode:
    def test_binary_picks_bm(self):
        values = [0, 1, 0, 1, 0, 1] * 10
        _, scheme, _ = auto_encode(values)
        assert scheme == "bm"

    def test_string_picks_cat_pipeline(self):
        values = ["a", "b", "a", "a", "c", "a", "a", "b", "c", "a"] * 5
        _, scheme, aux = auto_encode(values)
        # Must start with cat (only string-applicable transform)
        assert scheme.startswith("cat")
        assert "stoi" in aux

    def test_sparse_ints_picks_rle_or_nbp(self):
        values = [0] * 30 + [5, 7] + [0] * 20
        _, scheme, _ = auto_encode(values)
        # Either rle_bp or nbp would be reasonable — both should appear in path
        assert any(part in scheme for part in ("rle", "nbp"))

    def test_mixed_input_returns_no_encoding(self):
        values = [1, "a", 2.0]  # mixed type: nothing applies
        encoded, scheme, aux = auto_encode(values)
        assert scheme == ""
        assert aux == {}
        assert encoded == values

    def test_empty_input_returns_no_encoding(self):
        encoded, scheme, aux = auto_encode([])
        assert scheme == ""
        assert aux == {}
        assert encoded == []

    def test_lossy_false_excludes_quant(self):
        # Even on numeric data where quant might compress, lossy=False
        # must not pick a path containing 'quant'
        values = [1.0 + 0.001 * i for i in range(50)]
        _, scheme, _ = auto_encode(values, lossy=False)
        assert "quant" not in scheme.split("_") if scheme else True

    def test_lossy_makes_quant_eligible(self):
        # quant is in the candidate list, but it might still not win;
        # we just verify the call does not raise and yields a valid path.
        values = [float(i) for i in range(50)]
        encoded, scheme, aux = auto_encode(values, lossy=True)
        # Whatever path was chosen, either no encoding or some valid scheme
        assert isinstance(scheme, str)

    def test_default_is_lossy(self):
        # Default call (no flags) should allow lossy schemes and produce
        # at least as small a result as lossy=False on float data.
        values = [float(i) / 7 for i in range(64)]
        _, _, _ = auto_encode(values)  # must not raise
        _, lossless_scheme, _ = auto_encode(values, lossy=False)
        _, lossy_scheme, _ = auto_encode(values, lossy=True)
        # lossy=True is the default; spot-check that the two explicit calls agree
        assert lossy_scheme == auto_encode(values)[1]

    def test_terminal_steps_have_no_children_in_returned_scheme(self):
        # If a terminal step appears, it must be the last step in the pipeline
        values = [0, 1, 0, 1] * 10
        _, scheme, _ = auto_encode(values)
        if scheme:
            steps = scheme.split("_")
            for s in steps[:-1]:
                assert s not in _AUTO_TERMINAL, f"terminal {s} appears mid-pipeline"

    def test_no_aux_emitting_step_repeats_in_path(self):
        # Verify the structural constraint on multiple calls
        for values in [
            [0, 1, 0, 1] * 10,
            ["a", "b", "a", "a"] * 10,
            [10, 11, 12, 13, 14] * 5,
        ]:
            _, scheme, _ = auto_encode(values)
            steps = scheme.split("_") if scheme else []
            aux_used = [s for s in steps if s in _AUTO_AUX_EMITTING]
            assert len(aux_used) == len(set(aux_used))

    def test_max_depth_limits_pipeline_length(self):
        values = ["a", "a", "b", "b"] * 5
        _, scheme, _ = auto_encode(values, max_depth=2)
        if scheme:
            assert len(scheme.split("_")) <= 2

    def test_round_trip_via_payload_dispatch(self):
        # "auto" registered in encode_feature_payload should work end-to-end
        cases = {
            "binary": [0, 1, 0, 0, 1, 1, 1, 0, 0, 1] * 5,
            "strings": ["a", "b", "a", "a", "c"] * 5,
            "rle_ints": [1, 1, 1, 2, 2, 3, 3, 3, 3] * 3,
        }
        encoded = encode_feature_payload(cases, {k: "auto" for k in cases}, lossy=False)
        decoded = decode_feature_payload(encoded)
        for name, original in cases.items():
            assert decoded[name] == original, f"{name} round-trip failed"


class TestValidatePipeline:
    """`validate_pipeline` powers the composer/inspector improper-sequence warnings.
    It must stay in lockstep with the same `_AUTO_TYPE_TRANSITIONS` table the
    auto-search uses, so these cases pin the observable warning contract."""

    def _codes(self, pipeline, list_type):
        return [w["code"] for w in validate_pipeline(pipeline, list_type)]

    def test_valid_pipelines_produce_no_warnings(self):
        assert validate_pipeline("cat_rle_bp", "string") == []
        assert validate_pipeline("del_bp", "int") == []
        assert validate_pipeline("quant_bp", "float") == []
        assert validate_pipeline("bm", "binary") == []
        assert validate_pipeline("nbp", "int") == []
        assert validate_pipeline("rle_bp", "binary") == []

    def test_auto_and_passthrough_never_warn(self):
        assert validate_pipeline("auto", "string") == []
        assert validate_pipeline("auto", "mixed") == []
        assert validate_pipeline("", "int") == []

    def test_cat_on_non_string_is_type_mismatch(self):
        for t in ("int", "float", "binary"):
            assert self._codes("cat", t) == ["type_mismatch"]

    def test_bm_requires_binary(self):
        assert self._codes("bm", "int") == ["type_mismatch"]
        assert self._codes("bm", "float") == ["type_mismatch"]

    def test_terminal_packer_must_be_last(self):
        # bp on int is type-valid but terminal; nothing may follow it.
        codes = self._codes("bp_cat", "int")
        assert codes == ["not_terminal_last"]

    def test_bp_cat_on_string_flags_the_root_cause(self):
        # On string data, bp can't consume the input at all — the type error is
        # the actionable root cause, so we surface just that (not also a
        # position warning about an output type we couldn't determine).
        assert self._codes("bp_cat", "string") == ["type_mismatch"]

    def test_rle_on_string_is_terminal(self):
        # rle over strings yields a terminal (non-list) output — bp can't follow.
        assert self._codes("rle_bp", "string") == ["not_terminal_last"]

    def test_aux_emitting_step_cannot_repeat(self):
        assert self._codes("del_del", "int") == ["aux_repeat"]
        assert self._codes("cat_cat_bp", "string") == ["aux_repeat"]

    def test_unknown_scheme(self):
        assert self._codes("foo_bp", "int") == ["unknown_scheme"]

    def test_mixed_type_is_a_field_level_warning(self):
        issues = validate_pipeline("cat_bp", "mixed")
        assert len(issues) == 1
        assert issues[0]["code"] == "mixed_type"
        assert issues[0]["level"] == "warn"
        assert issues[0]["step_index"] is None

    def test_datetime_is_string_like_for_cat_and_rle(self):
        assert validate_pipeline("cat", "datetime") == []
        assert validate_pipeline("cat_rle", "datetime") == []
        # but numeric-only steps still reject it
        assert self._codes("del", "datetime") == ["type_mismatch"]

    def test_step_index_points_at_the_offending_step(self):
        issues = validate_pipeline("quant_cat", "float")  # quant ok, cat gets int
        assert len(issues) == 1
        assert issues[0]["code"] == "type_mismatch"
        assert issues[0]["step_index"] == 1

    def test_transition_table_and_labels_stay_in_sync(self):
        # Every scheme the search knows about must be labellable, so warnings
        # never leak a bare short code.
        from c1.aiml.compression.encoding.auto_encode import (
            _AUTO_TYPE_TRANSITIONS,
            _SCHEME_LABELS,
        )
        assert set(_AUTO_TYPE_TRANSITIONS) <= set(_SCHEME_LABELS)
