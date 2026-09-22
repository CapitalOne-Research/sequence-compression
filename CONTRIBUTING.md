# Contributing to seqpack

Thanks for your interest in contributing! This document covers how to set up a
development environment, the checks your PR needs to pass, and how to add a
new encoding scheme.

## Development setup

```bash
git clone https://github.com/CapitalOne-Research/sequence-compression.git
cd sequence-compression
pip install -e '.[spark,web,dev]'
```

The `dev` extra installs `pytest`, `pytest-cov`, `hypothesis`, `ruff`, and
`mypy`. `spark` and `web` are optional but recommended if you're touching
those code paths.

## Running the checks

```bash
# Tests (tests requiring PySpark or Hypothesis skip cleanly if those
# extras aren't installed)
python -m pytest tests/ -q

# Lint + format
python -m ruff check seqpack/
python -m ruff format --check seqpack/

# Type-check
python -m mypy seqpack/
```

All three run in CI on every PR; please run them locally first.

## Code style

- Follow the style already in the file you're editing — this codebase
  favors small, typed, docstringed functions with Google-style docstrings
  (`Args:` / `Returns:` / `Raises:`).
- Public functions should validate their inputs and raise a `seqpack`
  exception (see `seqpack/exceptions.py`) with an actionable message rather
  than letting an internal error propagate.
- New public entry points should be re-exported from `seqpack/__init__.py`
  (and added to `__all__`) if they're meant to be part of the supported API.

## Adding a new encoding scheme

Schemes live in matched pairs under `seqpack/encoding/schemes/` and
`seqpack/decoding/schemes/`, and are wired together through a few shared
registries. To add a scheme called `foo`:

1. **Encoder** — `seqpack/encoding/schemes/foo_encoding.py`, exposing
   `encode(values, **options) -> tuple[SchemeValue, AuxInfo]`.
2. **Decoder** — `seqpack/decoding/schemes/foo_decoding.py`, exposing
   `decode(value, **aux) -> list[Any]`, the exact inverse of `encode`.
3. **Registry** — add `"foo"` to `_ENCODING_NAMES` and `_DECODING_NAMES` in
   `seqpack/utils/lookup.py`.
4. **Wire schema** — if your scheme emits auxiliary info, add a `TypedDict`
   for it in `seqpack/wire.py` and register it in `AUX_SCHEMAS`. Its keys
   must exactly match your `decode()` function's parameter names —
   `tests/test_wire_golden.py` enforces this.
5. **Auto-discovery** — if the scheme should be reachable via `"auto"`,
   add its `(input_type -> output_type)` transition to
   `_AUTO_TYPE_TRANSITIONS` in `seqpack/encoding/auto_encode.py`, and decide
   whether it's a root seed, aux-emitting (can't repeat in a path), or
   terminal (can't have children).
6. **Docs** — add it to the scheme table and reference section in
   `README.md` and `seqpack/encoding_schemes.md`.
7. **Tests** — add a `tests/test_foo.py` covering round-trip correctness,
   edge cases (empty/constant/single-element input), and — if the scheme is
   lossy — a note that it's lossy. `tests/test_property_round_trips.py` and
   `tests/test_pipeline_matrix.py` exercise schemes generically; check
   whether your scheme needs an entry there too.

## Reporting bugs / requesting features

Please open a GitHub issue with a minimal reproduction (input values +
pipeline string) when reporting a bug.

## Security

Please do not open a public issue for security vulnerabilities — see
[SECURITY.md](SECURITY.md).
