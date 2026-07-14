# sequence-compression

A Python library for compressing feature sequences (lists of values) into compact JSON-serializable representations. Built for the Recommender Systems team; supports both a pandas path (single-machine) and a PySpark path (distributed).

## Overview

Each feature column holds a list of values (integers, floats, strings, or booleans). This library encodes those lists using composable pipelines of compression schemes, stores the result as a small JSON array, and provides a symmetric decoder. Encoding is always size-checked — if the encoded form is not strictly smaller than the original, the original is kept as-is.

## Installation

```bash
# Core library only (no Spark)
pip install .

# + PySpark support
pip install '.[spark]'

# + web server (tornado)
pip install '.[web]'

# + dev/test tools (pytest, plotly)
pip install '.[dev]'

# Everything
pip install '.[spark,web,dev]'
```

For local development (editable install):

```bash
pip install -e '.[spark,web,dev]'
```

## Quick start

```python
from c1.aiml.compression.encoding.feature_encode import encode_feature_df, encode_feature_payload
from c1.aiml.compression.decoding.feature_decode import decode_feature_payload

encoding_schema = {
    "item_ids":    "cat_rle_bp",   # fixed pipeline
    "scores":      "quant_bp",     # fixed pipeline
    "flags":       "bm",           # binary bitmap
    "counts":      ["rle", "bp"],  # pick best from candidates
    "embeddings":  "auto",         # depth-3 DFS over all valid pipelines
}

# Encode a DataFrame
encoded_df = encode_feature_df(df, encoding_schema)

# Encode a single payload dict
encoded_payload = encode_feature_payload(payload, encoding_schema)

# Decode back
decoded_payload = decode_feature_payload(encoded_payload)
```

---

## Encoding schema

Each key in the encoding schema maps a feature name to one of three forms:

| Form | Example | Behavior |
|------|---------|----------|
| Fixed pipeline string | `"cat_rle_bp"` | Always applies this pipeline (skips if it doesn't reduce size) |
| List of candidate pipelines | `["rle", "bp", "cat_bp"]` | Evaluates each, picks the one producing the smallest result |
| `"auto"` | `"auto"` | Runs a depth-3 DFS over all valid pipeline combinations, picks the smallest |

```python
encoding_schema = {
    "feature_a": "cat_bp",           # fixed pipeline
    "feature_b": ["rle", "cat_bp"],  # pick best from candidates
    "feature_c": "auto",             # DFS auto-discovery
}
```

---

## Encoding schemes

Schemes are combined by joining short codes with `_`. The encoder applies steps left-to-right; the decoder reverses them. Pipelines typically follow a **transform → reduce → pack** pattern.

### Overview

| Code    | Name                | Input    | Output          | Lossy   |
| ---------| ---------------------| ----------| -----------------| ---------|
| `cat`   | Categorical         | strings  | ints            | no      |
| `quant` | Scalar Quantization | floats   | ints in [0, 2ⁿ) | **yes** |
| `del`   | Delta               | numerics | numerics        | no      |
| `rle`   | Run-Length Encoding | any list | flat list       | no      |
| `stl`   | Sentinel            | numerics | numerics        | no      |
| `bm`    | Bitmap              | 0/1 ints | base64 string   | no      |
| `bp`    | Bit Packing         | ints     | base64 string   | no      |
| `nbp`   | Nullmap Bit-Packing | ints     | base64 string   | no      |
| `tbqm`  | TurboQuant MSE      | floats   | ints            | **yes** |
| `tbqp`  | TurboQuant Prod     | floats   | ints            | **yes** |

---

### Transform schemes

#### `cat` — Categorical encoding

Categorical encoding converts a sequence of strings into a sequence of integers by building a vocabulary — a one-to-one mapping from each unique string to a compact integer id. The vocabulary is constructed by ranking strings by frequency, so the most common string gets id `0`, the next most common gets id `1`, and so on; this frequency-sorted assignment means the most frequent values, which tend to appear most in the encoded output, are represented by the smallest integers and therefore require the fewest bits when packed. The full string→int map (`stoi`) is saved as auxiliary info and shipped alongside the encoded sequence so the decoder can invert the mapping exactly. Set `frequency_sorted=False` to assign ids in first-appearance order instead.

- **Auxiliary info**: `stoi` — `{string: int}` dict for decoding
- **Common pairings**: `cat_bp`, `cat_rle_bp`, `cat_rle`

```python
# [A, B, A, A, C] → ([0, 1, 0, 0, 2], {"stoi": {"A": 0, "B": 1, "C": 2}})
```

#### `quant` — Scalar Quantization _(lossy)_

Scalar quantization reduces the precision of floating-point values by projecting them onto a uniform grid of integers. The float range is divided into `2^num_bits` evenly-spaced buckets (default `num_bits=8`, giving 256 levels), and each value is rounded to the nearest bucket index. Two modes are used depending on the data's distribution: asymmetric mode maps `[min, max]` onto `[0, 2^n − 1]` using the formula `q = round((x − min) / scale)` where `scale = (max − min) / (2^n − 1)`, and is used for general data; symmetric mode maps the absolute range `[−abs_max, abs_max]` onto `[0, 2^n]` using `q = round(x / scale) + offset`, and is chosen when the data is roughly centered around zero (`|min + max| < 0.1 * (max − min)`). Both the scale and zero point are saved as auxiliary info so the decoder can apply the inverse linear transformation to reconstruct approximate float values. A constant input sequence is signaled by `q_scale=0.0`. Because values are rounded to a grid, some precision is permanently lost — the finer the grid (more bits), the smaller the error.

- **Auxiliary info**: `q_scale`, `q_zp` (zero point), `q_bits`, `q_sym` (1=symmetric, 0=asymmetric)
- **Common pairings**: `quant_bp`, `quant_nbp`

#### `tbqm` — TurboQuant MSE _(lossy)_

TurboQuant MSE treats the entire float list as a single d-dimensional vector and applies the TurboQuant_MSE algorithm (arXiv:2504.19874). It normalizes the vector, applies a seeded random rotation, and quantizes each rotated coordinate against a Lloyd-Max optimal codebook computed for the Beta distribution (the marginal of a uniform point on S^{d−1}). The random rotation distributes distortion uniformly across all coordinates, enabling near-optimal quantization for MSE at the chosen bit depth. The result is a plain list of integer codebook indices — compose with `bp` or `rle_bp` for the final packing step. Requires vector length ≥ 3.

- **Auxiliary info**: `tq_dim` (d), `tq_bits` (bits/coord, default 4), `tq_seed` (rotation seed), `tq_norm` (original vector norm)
- **Common pairings**: `tbqm_bp`, `tbqm_rle_bp`

#### `tbqp` — TurboQuant Prod _(lossy)_

TurboQuant Prod is a two-stage variant optimized for unbiased inner-product estimation rather than MSE. It runs `tbqm` with `(num_bits − 1)` bits, computes the residual between the normalized input and its MSE reconstruction, then applies QJL (quantized Johnson-Lindenstrauss): storing `sign(S · r)` for a random Gaussian matrix S. The QJL residual correction makes `<x̃, ỹ>` an unbiased estimator of `<x, y>` at the same total bit budget. The QJL signs are bitmap-encoded into the aux dict. The MSE indices are returned as a plain list of integers for downstream composition. Requires vector length ≥ 3 and `num_bits ≥ 2`.

- **Auxiliary info**: `tq_dim`, `tq_bits`, `tq_seed`, `tq_norm`, `tq_rnorm` (residual norm), `tq_qseed` (QJL seed), `tq_signs` (bitmap-encoded QJL signs)
- **Common pairings**: `tbqp_bp`, `tbqp_rle_bp`

---

### Reducer schemes

#### `del` — Delta encoding

Delta encoding exploits the fact that adjacent values in a sequence are often close together. Instead of storing each value absolutely, it stores the difference between consecutive elements: `d[i] = x[i] − x[i−1]`. When the original sequence is monotonic or slowly-varying, these differences are much smaller numbers than the originals, which reduces the number of bits needed to represent each element in a subsequent packing step. The first element has no predecessor, so it is saved as `v0` in auxiliary info; decoding reconstructs the original by computing a cumulative sum starting from `v0`. Works on both integers and floats.

- **Auxiliary info**: `v0` — first value of the original sequence
- **Common pairings**: `del_bp`

```python
# [100, 103, 107, 108] → ([3, 4, 1], {"v0": 100})
```

#### `rle` — Run-Length Encoding

Run-length encoding compresses sequences that contain long consecutive runs of the same value. Instead of repeating the value N times, it stores the pair `(value, N)` once. The default output is a flat interleaved list `[v0, c0, v1, c1, ...]` where each value is immediately followed by its run count — so a run of 1000 identical integers collapses to just two numbers regardless of its length. This is a lossless, order-preserving transformation that works on any element type (integers, floats, or strings), and the flat format carries no auxiliary info. It is most effective when the sequence has high repetition; sequences with no repeated values will actually expand (every element becomes a pair). Alternative output formats (`tuple`, `dict`) are also supported via the `return_type` argument to the encode function directly.

- **Auxiliary info**: none
- **Common pairings**: `rle`, `cat_rle`, `cat_rle_bp`, `rle_bp`

```python
# [A, A, A, B, B] → [A, 3, B, 2]
```

#### `stl` — Sentinel encoding

Some numeric sequences contain a small number of extreme outlier values — sentinel-like "null" markers such as `-9999` or `0` — mixed in with a tight cluster of regular values. Those outliers inflate the value range and force downstream bit-packers to allocate many more bits per element for the entire sequence. Sentinel encoding identifies these outliers using an IQR fence: any value beyond `median ± iqr_factor * IQR` (default `iqr_factor=3.0`) is classified as a sentinel; for nearly-constant data it falls back to `median ± 1`. The sentinels are stripped out, leaving a clean sequence with a much narrower range, and their original positions are recorded as compact integer ranges in auxiliary info (`snt_ranges`). The decoder splices the sentinels back in at those positions to reconstruct the original sequence exactly. If no values exceed the fence, the sequence is returned unchanged.

- **Auxiliary info**: `snt_ranges` — `{value: [[start, end], ...]}` of sentinel positions (single-element ranges stored as `[pos]`); `length` — original sequence length
- **Common pairings**: `stl_bp`

---

### Packer schemes (produce base64-encoded binary blobs)

These are terminal steps — they produce compact base64 strings and cannot have children in a pipeline. They use frame-of-reference (FOR: subtract min to make values non-negative) and `numpy.packbits`.

#### `bm` — Bitmap

A bitmap is the most compact possible representation for a binary sequence: each element occupies exactly one bit. The encoder allocates one bit per value in the sequence, packing them MSB-first into bytes. A 2-byte header precedes the payload and encodes two things: the total element count (14 bits, supporting up to 16,383 elements) and a constant flag. When every element in the sequence is the same value (all `0`s or all `1`s), the constant flag is set and no payload bytes are written at all — the single repeated value and the count are sufficient to reconstruct the sequence, so the entire encoding fits in just 2 bytes. The final blob is base64-encoded for safe JSON transport.

- **Auxiliary info**: none

#### `bp` — Bit Packing

Standard integer compression works by observing that a list of integers rarely needs the full 32 or 64 bits per element that a general-purpose type would allocate — if all values fall within a range of `[50, 100]`, for example, only 6 bits per value are needed rather than 64. Bit packing formalizes this: it first applies frame-of-reference (FOR) by subtracting the minimum value from every element, shifting the range to start at zero. It then determines the minimum number of bits required to represent the largest value in the shifted range, and packs all elements at that fixed bit width, MSB-first. The minimum (the FOR offset), the bit width, and the element count are all written into a compact binary header so the decoder can reverse the process without any separate auxiliary info. Constant sequences (all elements identical) are a degenerate case — they need no payload at all, just the header.

- **Auxiliary info**: none (everything is in the binary blob)

#### `nbp` — Nullmap Bit-Packing

Standard bit packing allocates the same bit width to every element based on the widest value in the sequence. This is inefficient for sparse sequences — sequences where one value (e.g. `0`) accounts for the vast majority of entries but a few outlier values are wide — because those few wide values force all elements, including the dominant ones, to use a large bit width. Nullmap bit-packing separates the two populations: the dominant value is identified by frequency and stored once in the header; a compact 1-bit-per-element nullmap then marks which positions hold non-dominant values (1) versus the dominant value (0). The non-dominant values are collected into their own list, frame-of-reference adjusted against their own minimum, and bit-packed at a width determined only by their own range — completely independent of the dominant value. The decoder reads the nullmap to know where to place each non-dominant value and fills everything else with the dominant. If the sequence is entirely dominant, no nullmap or payload is written at all.

- **Auxiliary info**: none

---

## Pipeline composition

Steps are joined with `_` and applied left-to-right during encoding, right-to-left during decoding:

```
"cat_rle_bp"
 encode: cat → rle → bp
 decode: bp⁻¹ → rle⁻¹ → cat⁻¹
```

### Recommended pipelines by data shape

| Data shape                           | Recommended pipeline                          |
| --------------------------------------| -----------------------------------------------|
| Categorical strings with long runs   | `cat_rle` or `cat_rle_bp`                     |
| Categorical strings, no runs         | `cat_bp`                                      |
| Smooth float sequence                | `quant_bp`                                    |
| Sparse integers (one dominant value) | `nbp` or `cat_nbp`                            |
| Binary feature (0/1 only)            | `bm`                                          |
| Numerics with stray outliers/nulls   | `stl_bp`                                      |
| Sorted timestamps                    | `del_bp`                                      |
| Unknown — let the library decide     | `"auto"` or `["cat_bp", "cat_rle_bp", "rle"]` |

---

## Auto-discovery

Setting a feature's schema to `"auto"` runs a depth-3 DFS over all valid pipeline combinations and returns the one that produces the smallest encoded output.

```python
encoding_schema = {"my_feature": "auto"}
encoded_df = encode_feature_df(df, encoding_schema)
```

- Root seeds are type-specific: binary data only considers `bm/nbp/rle` at depth 0, not e.g. `del` (which would expand the value range).
- Aux-emitting steps (`cat`, `del`, `quant`, `stl`) cannot repeat in a path.
- Terminal packers (`bm`, `bp`, `nbp`) cannot have children.
- Pruning is structural only — the search continues through transient size increases (e.g. `cat` alone is larger than its input, but `cat_rle_bp` may be much smaller).
- In `encode_feature_df`, `"auto"` is resolved per row, so different rows of the same column may end up with different concrete pipelines.
- Pass `allow_lossy=True` to `auto_encode()` directly to include `quant` in the search.

---

## Encoded record

`encode_feature_payload` stores each feature as `<feature_name>_enc` containing a JSON-serialized array:

```json
[encoded_value, "encoding_scheme_string", {"aux_key": "aux_value"}]
```

- The scheme string is omitted when no encoding was applied.
- Auxiliary info is omitted when empty.
- Encoding is only applied when the encoded form is strictly smaller than the original.

Example output for a payload with one feature:

```python
{"item_ids_enc": '[[0,1,0,2,0], "cat_bp", {"stoi": {"A": 0, "B": 1, "C": 2}}]'}
```

---

## Pandas API

### Encoding

```python
from c1.aiml.compression.encoding.feature_encode import (
    encode_feature_df,       # encode a whole DataFrame
    encode_feature_payload,  # encode a single dict
    encode_feature,          # encode a single value with a fixed pipeline
    evaluate_candidates,     # evaluate a list of pipeline candidates
)

# Encode a DataFrame (returns a new DataFrame with _enc columns)
encoded_df = encode_feature_df(df, encoding_schema)

# Keep both original and encoded columns
encoded_df = encode_feature_df(df, encoding_schema, drop_originals=False)

# Include payload size metrics (adds encoded_size and payload_size columns)
encoded_df = encode_feature_df(df, encoding_schema, metrics=True)

# Encode a single dict payload
encoded = encode_feature_payload({"item_ids": [1, 2, 3]}, {"item_ids": "bp"})

# encoding_schema is optional — omit it to auto-encode all list columns
encoded = encode_feature_payload({"item_ids": [1, 2, 3]})
```

### Decoding

```python
from c1.aiml.compression.decoding.feature_decode import (
    decode_feature_payload,  # decode a dict produced by encode_feature_payload
    decode_feature,          # decode a single encoded value
)

decoded = decode_feature_payload(encoded_payload)
```

---

## Spark API

### Encoding

```python
from c1.aiml.compression.encoding.spark_feature_encode import encode_feature_dataframe

schema = {"feature_a": "cat_bp", "feature_b": ["rle", "bp"]}

# Returns a Spark DataFrame with _enc columns
encoded_spark_df = encode_feature_dataframe(spark_df, schema)

# With metrics columns: size_before_bytes, size_after_bytes, sequence_length
encoded_spark_df = encode_feature_dataframe(spark_df, schema, metrics=True)
```

### Decoding

```python
from c1.aiml.compression.decoding.spark_feature_decode import decode_feature_dataframe

# Auto-detect all _enc columns and decode them
decoded_spark_df = decode_feature_dataframe(encoded_spark_df)

# Decode specific columns only
decoded_spark_df = decode_feature_dataframe(
    encoded_spark_df,
    encoded_columns=["feature_a_enc", "feature_b_enc"],
)

# Keep encoded columns alongside decoded ones
decoded_spark_df = decode_feature_dataframe(encoded_spark_df, drop_originals=False)
```

---

## Analysis utilities

### Encoding distribution

```python
from c1.aiml.compression.utils.metrics import encoding_counter, encoding_counter_spark

# pandas — returns a DataFrame: rows = features, columns = scheme codes
counts = encoding_counter(encoded_df)

# Spark — returns a pandas DataFrame with a feature_name column
counts = encoding_counter_spark(encoded_spark_df)
```

### Compression metrics (Spark)

```python
from c1.aiml.compression.utils.metrics import print_compression_metrics

# Requires metrics=True when encoding
print_compression_metrics(encoded_spark_df)
# Prints: dataset overview, sequence length stats (if present), payload size stats,
#         compression ratio, size reduction %, bytes saved
```

### Quantization loss

```python
from c1.aiml.compression.utils.metrics import quantization_loss

metrics = quantization_loss(original_floats, reconstructed_floats)
# Returns: mae, max_ae, rmse, mre, snr_db, cosine_sim
```

### Latency benchmarking

```python
from c1.aiml.compression.utils.benchmark import run_benchmark

raw_results, agg, fig = run_benchmark(
    df,
    encoding_schema={"feature_a": "cat_rle_bp", "feature_b": ["rle", "bp"]},
    output_dir="./benchmark_output",  # saves HTML + PNG charts
    percentiles=[75, 95, 99],         # default
)
# Prints a summary table and produces a plotly bar chart comparing
# encode/decode latency per scheme (* suffix = lossy)
```

`encoding_schema` can also be a path to a JSON file containing the schema dict.

The benchmark module exposes lower-level functions for custom workflows:

```python
from c1.aiml.compression.utils.benchmark import (
    benchmark_dataframe,   # raw latency measurements per feature × row × scheme
    aggregate_results,     # aggregate into per-scheme summary DataFrame
    plot_results,          # produce plotly figure from aggregated results
    print_summary_table,   # print formatted latency table to stdout
)
```

---

## Web UI

A browser-based Compression Playground for interactive exploration.

**Setup** (requires the `web` extra):

```bash
pip install '.[web]'
```

**Run** from the repo root:

```bash
python -m web.server        # defaults to port 8765
python -m web.server 9000   # custom port
```

Then open `http://localhost:8765/`.

### Pages

- **Encoder** (`/`) — upload a CSV/Parquet file, inspect column profiles, compose pipelines, and see per-column compression results with a scheme distribution histogram.
- **Inspector** (`/inspector.html`) — paste any sequence, pick a pipeline (or `auto`), and walk through each intermediate step: dictionary build-up for `cat`, run highlighting for `rle`, delta values for `del`, hex bytes for bit-packing schemes.

### API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/inspect` | POST | Multipart file upload. Returns per-column profile: inferred type, cardinality, samples, byte size, recommended pipeline. |
| `/api/encode` | POST | Multipart file + `schema` JSON. Returns per-column metrics, scheme histogram, and the `[value, scheme, aux]` encoded record from row 1. |
| `/api/steps` | POST | JSON body `{values, pipeline, allow_lossy?}`. Returns each intermediate pipeline step with values, aux dict, and byte size. Use `pipeline: "auto"` to resolve and then walk the discovered pipeline. |

---

## Repository structure

```
c1/aiml/compression/
├── encoding/
│   ├── feature_encode.py        # encode_feature_df, encode_feature_payload
│   ├── spark_feature_encode.py  # encode_feature_dataframe (Spark)
│   ├── auto_encode.py           # auto_encode, _infer_list_type
│   └── schemes/
│       ├── bm_encoding.py
│       ├── bp_encoding.py
│       ├── cat_encoding.py
│       ├── delta_encoding.py
│       ├── nbp_encoding.py
│       ├── quant_encoding.py
│       ├── rle_encoding.py
│       └── stl_encoding.py
├── decoding/
│   ├── feature_decode.py        # decode_feature_payload, decode_feature
│   ├── spark_feature_decode.py  # decode_feature_dataframe (Spark)
│   └── schemes/                 # symmetric decode modules
├── utils/
│   ├── sizing.py                # get_json_byte_size, _ensure_list
│   ├── metrics.py               # quantization_loss, encoding_counter, print_compression_metrics
│   ├── benchmark.py             # run_benchmark, benchmark_dataframe, aggregate_results, plot_results
│   ├── bitpack.py               # pack_bits, encode_count, encode_signed_varint
│   ├── lookup.py                # ENCODING_SCHEMES, DECODING_SCHEMES registries
│   └── spark_udfs.py            # PySpark Pandas UDFs
└── encoding_schemes.md          # full scheme reference with encoded record details
web/
├── server.py                    # Tornado backend
├── index.html + app.js          # Encoder page
├── inspector.html + inspector.js # Inspector page
├── schemes.html + schemes.js + schemes.css # Scheme reference browser
├── recsys-use-case.html         # RecSys use-case demo
├── sample_datasets/             # Sample parquet files for the UI
└── styles.css                   # Shared styles
```
