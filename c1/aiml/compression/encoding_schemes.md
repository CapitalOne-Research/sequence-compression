# Encoding Schemes

Each scheme is a `(encode, decode)` module pair under `c1/aiml/compression/encoding/schemes/` and `c1/aiml/compression/decoding/schemes/`. The encoder returns `(encoded_value, auxiliary_info)`; the decoder takes the encoded value plus any aux keys it needs and returns the original sequence.

Schemes compose in pipelines via underscore-joined short codes (e.g. `cat_rle_bp`). The encoder applies steps left-to-right; the decoder reverses them. Pipelines are typically structured as **transform → reduce → pack**.

## Quick reference

| Code    | Name                | Input    | Output          | Lossy   | Typical use                                          |
| ---------| ---------------------| ----------| -----------------| ---------| ------------------------------------------------------|
| `cat`   | Categorical         | strings  | ints            | no      | dictionary-encode strings to ints                    |
| `quant` | Scalar Quantization | floats   | ints in [0, 2ⁿ) | **yes** | reduce float precision                               |
| `del`   | Delta               | numerics | numerics        | no      | exploit small deltas in monotonic / smooth sequences |
| `rle`   | Run-Length          | any list | flat list       | no      | sequences with long runs of equal values             |
| `stl`   | Sentinel            | numerics | numerics        | no      | strip outlier "null" values to narrow value range    |
| `bm`    | Bitmap              | 0/1 ints | base64 string   | no      | binary sequences                                     |
| `bp`    | Bit Packing         | ints     | base64 string   | no      | general integer compression                          |
| `nbp`   | Nullmap Bit-Packing | ints     | base64 string   | no      | sparse sequences with one dominant value             |
| `tbqm`  | TurboQuant MSE      | floats   | ints            | **yes** | dense float vectors (d ≥ 3), MSE-optimal             |
| `tbqp`  | TurboQuant Prod     | floats   | ints            | **yes** | dense float vectors (d ≥ 3), inner-product-optimal   |

---

## Transforms (change representation)

### `cat` — Categorical encoding

Maps each unique string to an integer id. By default the most-frequent value gets id `0`, the next `1`, etc. — this assigns shorter bit widths to common values, which helps downstream `bp`. Set `frequency_sorted=False` to keep first-appearance order instead.

- **Output**: list of ints
- **Auxiliary info**: `stoi` — `{string: int}` map for decoding
- **Common pairings**: `cat_bp`, `cat_rle_bp`, `cat_rle`

### `quant` — Scalar Quantization (lossy)

Maps floats to unsigned integers in `[0, 2^num_bits - 1]`. Auto-selects asymmetric or symmetric mode based on whether the data is roughly centered around zero:

- **Asymmetric**: `q = round((x - min) / scale)`, `scale = (max - min) / (2ⁿ - 1)`
- **Symmetric**: `q = round(x / scale) + offset`, `scale = abs_max / (2ⁿ⁻¹ - 1)`

A constant input sequence is signaled by `q_scale=0.0`. Default `num_bits=8`.

- **Output**: list of ints
- **Auxiliary info**: `q_scale`, `q_zp` (zero point), `q_bits`, `q_sym` (1 = symmetric, 0 = asymmetric)
- **Common pairings**: `quant_bp`, `quant_nbp`
- **Loss metrics**: see `c1/aiml/compression/utils/metrics.py:quantization_loss` for MAE / RMSE / SNR

### `tbqm` — TurboQuant MSE (lossy)

Treats the entire float list as a single **d-dimensional vector** and applies the TurboQuant_MSE algorithm from arXiv:2504.19874:

1. Normalize the vector and store its norm.
2. Apply a seeded random rotation (PCG64-based, platform-independent).
3. Quantize each rotated coordinate against a Lloyd-Max optimal codebook computed for the exact Beta distribution (the marginal distribution of a uniform point on S^{d-1}).

This exploits the fact that random rotation distributes distortion uniformly across all coordinates, enabling near-optimal quantization for MSE.

- **Input**: list of floats with **d ≥ 3**
- **Output**: list of ints (codebook indices) — compose with `bp` or `rle_bp` for final packing
- **Auxiliary info**: `tq_dim` (d), `tq_bits` (bits/coord, default 4), `tq_seed` (rotation seed), `tq_norm` (original vector norm)
- **Lossy**: reconstruction error ≈ `O(1/2^num_bits)` per coordinate
- **Auto**: selected by `auto_encode` when `allow_lossy=True` and input is float with len ≥ 3
- **Common pairings**: `tbqm_bp`, `tbqm_rle_bp`

### `tbqp` — TurboQuant Prod (lossy)

Two-stage variant optimized for **unbiased inner-product estimation** rather than MSE:

1. Run `tbqm` with `(num_bits - 1)` bits.
2. Compute residual `r = x_normalized - x_mse`.
3. Apply QJL (quantized Johnson-Lindenstrauss): store `sign(S · r)` where S is a random Gaussian matrix.

Total bit budget per coordinate = `(num_bits - 1) + 1 = num_bits`. The QJL residual correction makes the inner product `<x̃, ỹ>` an **unbiased estimator** of `<x, y>`.

- **Input**: list of floats with **d ≥ 3**
- **Output**: list of ints (MSE codebook indices) — compose with `bp` or `rle_bp` for final packing
- **Auxiliary info**: `tq_dim`, `tq_bits` (≥ 2), `tq_seed`, `tq_norm`, `tq_rnorm` (residual norm), `tq_qseed` (QJL seed), `tq_signs` (bitmap-encoded QJL signs)
- **Lossy**: higher RMSE than `tbqm` at same bit budget, but better for dot-product / cosine similarity downstream tasks
- **Common pairings**: `tbqp_bp`, `tbqp_rle_bp`

---

## Reducers (shrink the value range or sequence length)

### `del` — Delta

Replaces each value with the difference from its predecessor. The first value is stored in `v0` so the sequence can be reconstructed. Best for monotonic or smooth sequences where deltas are small.

- **Output**: list of differences (one shorter than input)
- **Auxiliary info**: `v0` — first value of the original sequence
- **Common pairings**: `del_bp`

### `rle` — Run-Length Encoding

Replaces runs of equal values with `[value, count]` pairs. The default `flat` output format is `[v0, c0, v1, c1, ...]`; `tuple` and `dict` output formats are also supported via the `return_type` argument.

- **Output**: flat list `[v0, c0, v1, c1, ...]`
- **Auxiliary info**: none
- **Common pairings**: `rle`, `cat_rle`, `cat_rle_bp`, `rle_bp`

### `stl` — Sentinel

Detects outlier "sentinel" values using the IQR method, strips them from the sequence, and stores their positions separately. This narrows the value range for downstream packers — e.g. `bp` may drop from 11 bits to 6 bits when stray `0`s are removed from a `[1827..1865]` range.

- **Output**: clean list (input with sentinels removed)
- **Auxiliary info**:
  - `snt_ranges` — `{value: [[start, end], ...]}` of sentinel positions, with single-element ranges as `[pos]`
  - `length` — original sequence length
- **Sentinel detection**: any value beyond `median ± iqr_factor * IQR` (default `iqr_factor=3.0`); falls back to `median ± 1` for nearly-constant data. Returns the input unchanged if no outliers are found.
- **Common pairings**: `stl_bp`, `cat_stl_bp`

---

## Bit-level packers (produce base64-encoded binary blobs)

These output base64 strings and share several techniques: varint count headers, frame-of-reference (FOR — subtract min so all values are non-negative), and `numpy.packbits` for the bit-level packing. They are typically the final step of a pipeline.

### `bm` — Bitmap

For binary `0/1` sequences. 2-byte header encodes a 14-bit count and a constant-flag bit. Constant-all-`0` or all-`1` sequences need no payload (just the header). Max length: 16,383.

- **Input**: list of `0`/`1` ints
- **Output**: base64 string
- **Auxiliary info**: none
- **Header layout** (2 bytes):
  - byte 0: low 8 bits of count
  - byte 1: `[count_hi(6) | constant_value(1) | constant_flag(1)]`
- **Payload**: `⌈count/8⌉` bytes of bits, MSB first (omitted when constant_flag is set)

### `bp` — Bit Packing

General-purpose integer packer. Computes the minimum bits-per-value from the data range, applies FOR (subtract min), then packs values MSB-first. Constant sequences are stored as a single value with no payload.

- **Input**: list of ints (signed OK)
- **Output**: base64 string
- **Auxiliary info**: none — everything is in the binary blob
- **Header**: `[bits_per_value: 1B][flags: 1B][count: 2 or 4B][optional FOR min: signed varint]`
- **Flags**:
  - `HAS_ZIGZAG (0x01)` — zigzag encoding applied (currently unused since FOR makes values non-negative)
  - `HAS_FOR (0x02)` — frame-of-reference; FOR min stored in header
  - `IS_CONSTANT (0x04)` — single value, no payload
  - `SHORT_COUNT (0x08)` — count fits in 2 bytes (else 4)

### `nbp` — Nullmap Bit-Packing

For sparse sequences where one dominant value accounts for a large fraction of entries. Stores the dominant value once, plus a 1-bit-per-element nullmap marking non-dominant positions, plus the non-dominant values bit-packed with FOR. The all-dominant case skips both the nullmap and the payload.

- **Input**: list of ints
- **Output**: base64 string
- **Auxiliary info**: none
- **Binary layout**:
  ```
  [flags: 1B][count: 2 or 4B][dominant: signed varint]
  [bits_per_value: 1B][FOR min: signed varint]
  [nullmap: ⌈count/8⌉ bytes, 1 = non-dominant, MSB first]
  [packed non-dominant values: bit-packed with FOR]
  ```
- **Flags**:
  - `SHORT_COUNT (0x01)` — count fits in 2 bytes
  - `ALL_DOMINANT (0x02)` — every value equals dominant, no nullmap or payload follows

---

## Pipeline patterns

| Data shape                           | Recommended pipeline      |
| --------------------------------------| ---------------------------|
| Categorical strings, repeating       | `cat_rle` or `cat_rle_bp` |
| Categorical strings, no runs         | `cat_bp`                  |
| Smooth float sequence                | `quant_bp`                |
| Dense float vector (embedding, score)| `tbqm` or `tbqp`          |
| Sparse integers (one dominant value) | `nbp` or `cat_nbp`        |
| Binary feature                       | `bm`                      |
| Numeric with stray nulls/outliers    | `stl_bp`                  |

When unsure, declare a candidate list (e.g. `["cat_bp", "cat_rle_bp", "cat_rle"]`) — `_evaluate_candidates` in `c1/aiml/compression/encoding/feature_encode.py` measures each and picks the smallest result.

## Wire format

`encode_feature_payload` stores each feature as `<feature_name>_enc` containing a JSON-serialized array:

```json
[encoded_value, encoding_scheme_string, auxiliary_info]
```

The scheme string is omitted when no encoding was applied; auxiliary info is omitted when empty. Encoding is only applied when the encoded form is strictly smaller than the original (size measured with `c1/aiml/compression/utils/sizing.py:get_json_byte_size`).
