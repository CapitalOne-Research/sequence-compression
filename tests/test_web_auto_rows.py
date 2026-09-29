"""Tests for the playground's /api/auto-rows endpoint (auto-encoding page)."""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("tornado")
pytest.importorskip("pandas")

from tornado.testing import AsyncHTTPTestCase  # noqa: E402

_SERVER_PATH = Path(__file__).resolve().parent.parent / "web" / "server.py"
_spec = importlib.util.spec_from_file_location("playground_server", _SERVER_PATH)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


class TestAutoRows(AsyncHTTPTestCase):
    def get_app(self):
        return server.make_app()

    def get_json(self, url, status=200):
        res = self.fetch(url, request_timeout=120)
        assert res.code == status, res.body
        return json.loads(res.body)

    def test_lists_columns(self):
        body = self.get_json("/api/auto-rows")
        assert "is_like" in body["columns"]
        assert body["default"] == "is_like"
        assert body["row_count"] > 0

    def test_column_gets_several_pipelines(self):
        body = self.get_json("/api/auto-rows?column=is_like")
        schemes = {r["scheme"] for r in body["rows"]}
        assert len(schemes) > 1
        assert sum(b["count"] for b in body["breakdown"]) == body["row_count"]
        assert body["totals"]["auto"] < body["totals"]["original"]
        for r in body["rows"]:
            assert r["enc_bytes"] <= r["orig_bytes"]

    def test_auto_never_loses_to_a_fixed_pipeline(self):
        for column in ("is_like", "date", "tab", "comment_stay_time"):
            body = self.get_json(f"/api/auto-rows?column={column}")
            assert body["fixed"], column
            assert body["fixed"][0]["bytes"] >= body["totals"]["auto"], column

    def test_single_row_returns_full_sequence(self):
        body = self.get_json("/api/auto-rows?column=is_like")
        first = body["rows"][0]
        row = self.get_json("/api/auto-rows?column=is_like&row=0")
        assert len(row["values"]) == first["length"]
        assert row["scheme"] == first["scheme"]

    def test_rejects_unknown_column_and_bad_row(self):
        self.get_json("/api/auto-rows?column=nope", status=400)
        self.get_json("/api/auto-rows?column=is_like&row=-1", status=400)
        self.get_json("/api/auto-rows?column=is_like&row=100000", status=400)

    def test_synthetic_column_shrinks_largest_row(self):
        meta = self.get_json("/api/auto-rows")
        column = meta["synthetic"]
        assert column in meta["columns"]

        body = self.get_json(f"/api/auto-rows?column={column}")
        assert set(body["profiles"]) == {"skimmer", "binger", "steady", "glitch"}
        assert {r["profile"] for r in body["rows"]} == set(body["profiles"])

        # The glitch users get stl, and stl explains which values it set aside.
        stl_rows = [r for r in body["rows"] if r["scheme"].startswith("stl")]
        assert stl_rows and all(r["profile"] == "glitch" for r in stl_rows)
        assert all(r["traits"]["outliers"]["count"] > 0 for r in stl_rows)

        # Per user, auto never loses to the best single pipeline, and it
        # shrinks the column's largest row, not just its total.
        best = body["fixed"][0]
        assert all(r["enc_bytes"] <= r["fixed_bytes"] for r in body["rows"])
        assert body["totals"]["auto"] < best["bytes"]
        assert body["totals"]["max_auto"] < best["max_bytes"] * 0.75

    def test_synthetic_column_is_deterministic(self):
        a, _ = server._synthetic_watch_ms(20)
        b, _ = server._synthetic_watch_ms(20)
        assert a == b
