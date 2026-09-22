# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial release: pandas and PySpark encode/decode APIs for compressing
  feature sequences into compact, JSON-serializable records, with ten
  composable encoding schemes (`cat`, `quant`, `del`, `rle`, `stl`, `bm`,
  `bp`, `nbp`, `tbqm`, `tbqp`), `"auto"` pipeline discovery, and analysis
  utilities (`metrics`, `benchmark`).
- Top-level public API — `encode_feature_df`, `encode_feature_payload`,
  `encode_feature`, `evaluate_candidates`, `auto_encode`,
  `decode_feature_payload`, `decode_feature`, and `EncodedEntry` are
  importable directly from `seqpack`, along with `seqpack.__version__`.
- A `seqpack.exceptions` hierarchy (`SeqPackError`, `InvalidInputError`,
  `UnknownSchemeError`, `DecodingError`) for public API errors, each also
  subclassing the builtin it replaces (`TypeError`/`ValueError`) so
  `except ValueError`/`except TypeError` code keeps working. Input
  validation on `encode_feature_df` (must be a `pandas.DataFrame`),
  `encode_feature_payload`/`decode_feature_payload` (must be a `dict`), and
  malformed wire-format records now raise clear, typed errors.
- A browser-based compression playground (`web/`).
