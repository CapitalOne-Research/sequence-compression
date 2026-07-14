"""TurboQuant MSE encoder — scheme code `tbqm`.

Applies the TurboQuant_MSE algorithm (arXiv:2504.19874):
  1. Normalize the input vector and store its norm.
  2. Apply a seeded random rotation.
  3. Quantize each coordinate using a Lloyd-Max codebook optimal for the
     resulting Beta distribution.

Output is a plain list of integer codebook indices so the result can be
composed with downstream pipeline steps (e.g. tbqm_bp, tbqm_rle_bp).
All decoding parameters are stored in the returned aux dict using `tq_`-prefixed keys.
"""

from typing import List

import numpy as np

from c1.aiml.compression.utils.turbo_quant_config import TurboQuantConfig
from c1.aiml.compression.utils.turbo_quant_codebook import get_codebook_array, quantize_vector
from c1.aiml.compression.utils.turbo_quant_rotation import get_rotation_matrix, rotate


def encode(
    values: List[float] | np.ndarray,
    num_bits: int = 4,
    seed: int = 42,
) -> tuple[list, dict]:
    """Encode a float vector using TurboQuant MSE (lossy).

    Args:
        values: Input vector of floats. Must have length >= 3.
        num_bits: Bits per coordinate (1-8). Default 4.
        seed: Random seed for reproducible rotation matrix.

    Returns:
        Tuple of (indices, aux_dict). indices is a plain list of integer
        codebook indices in [0, 2^num_bits). The aux dict contains tq_dim,
        tq_bits, tq_seed, tq_norm needed for decoding.
    """
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError("Input must be a 1-dimensional vector")
    if len(x) < 3:
        raise ValueError("tbqm requires vector length >= 3 (codebook constraint)")
    if num_bits < 1 or num_bits > 8:
        raise ValueError("num_bits must be between 1 and 8")

    d = len(x)
    norm = float(np.linalg.norm(x))
    x_normalized = x / norm if norm > 0 else x

    Pi = get_rotation_matrix(d, seed)
    y = rotate(x_normalized, Pi)
    codebook = get_codebook_array(num_bits, d)
    indices = quantize_vector(y, codebook)

    config = TurboQuantConfig(dimension=d, num_bits=num_bits, seed=seed, variant="mse", norm=norm)
    aux = config.to_dict()
    del aux["tq_rnorm"]
    del aux["tq_qseed"]

    return indices.tolist(), aux
