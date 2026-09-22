"""TurboQuant prod encoder — scheme code `tbqp`.

Two-stage algorithm (arXiv:2504.19874, TurboQuant_prod):
  1. Run TurboQuant MSE with (num_bits - 1) bits.
  2. Compute the residual r = x_normalized - x_mse.
  3. Apply QJL to the residual: sign(S · r), giving an unbiased inner-product
     correction at the cost of 1 bit per coordinate.

Output is a plain list of MSE codebook indices (ints) so the result can be
composed with downstream pipeline steps. The QJL signs and residual norm are
stored in aux under tq_signs and tq_rnorm respectively.
"""

from typing import List

import numpy as np

from seqpack.utils.turbo_quant_config import TurboQuantConfig
from seqpack.utils.turbo_quant_codebook import get_codebook_array, quantize_vector, dequantize_indices
from seqpack.utils.turbo_quant_rotation import get_rotation_matrix, rotate, inverse_rotate
from seqpack.utils.qjl import get_projection_matrix, qjl_encode
from seqpack.encoding.schemes.bm_encoding import encode as bm_encode


def encode(
    values: List[float] | np.ndarray,
    num_bits: int = 4,
    seed: int = 42,
    qjl_seed: int = 43,
) -> tuple[list, dict]:
    """Encode a float vector using TurboQuant prod (lossy, inner-product optimal).

    Args:
        values: Input vector of floats. Must have length >= 3.
        num_bits: Total bits per coordinate (2-8). Default 4.
        seed: Random seed for rotation matrix.
        qjl_seed: Random seed for QJL projection matrix.

    Returns:
        Tuple of (mse_indices, aux_dict). mse_indices is a plain list of
        integer codebook indices in [0, 2^(num_bits-1)). The aux dict contains
        tq_dim, tq_bits, tq_seed, tq_norm, tq_rnorm, tq_qseed, tq_signs.
    """
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError("Input must be a 1-dimensional vector")
    if len(x) < 3:
        raise ValueError("tbqp requires vector length >= 3 (codebook constraint)")
    if num_bits < 2 or num_bits > 8:
        raise ValueError("num_bits must be between 2 and 8 for tbqp")

    d = len(x)
    mse_bits = num_bits - 1

    norm = float(np.linalg.norm(x))
    x_normalized = x / norm if norm > 0 else x

    Pi = get_rotation_matrix(d, seed)
    y = rotate(x_normalized, Pi)
    codebook = get_codebook_array(mse_bits, d)
    indices = quantize_vector(y, codebook)

    y_reconstructed = dequantize_indices(indices, codebook)
    x_reconstructed_normalized = inverse_rotate(y_reconstructed, Pi)
    residual = x_normalized - x_reconstructed_normalized
    residual_norm = float(np.linalg.norm(residual))

    S = get_projection_matrix(d, qjl_seed)
    qjl_signs = qjl_encode(residual, S)
    # Map {-1, +1} → {0, 1} and bitmap-encode for compact aux storage.
    signs_binary = ((qjl_signs + 1) // 2).tolist()
    tq_signs_bm, _ = bm_encode(signs_binary)

    config = TurboQuantConfig(
        dimension=d, num_bits=num_bits, seed=seed, variant="prod",
        norm=norm, residual_norm=residual_norm, qjl_seed=qjl_seed,
    )
    aux = config.to_dict()
    aux["tq_signs"] = tq_signs_bm

    return indices.tolist(), aux
