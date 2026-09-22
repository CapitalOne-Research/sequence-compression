"""TurboQuant prod decoder — scheme code `tbqp`.

Reconstructs a float vector from TurboQuant_prod encoded data:
  1. Look up centroid values for the MSE codebook indices.
  2. Inverse-rotate to recover the MSE normalized vector.
  3. Reconstruct QJL correction from tq_signs and tq_rnorm in aux.
  4. Combine and denormalize.
"""

from typing import List

import numpy as np

from seqpack.utils.turbo_quant_config import TurboQuantConfig
from seqpack.utils.turbo_quant_codebook import get_codebook_array, dequantize_indices
from seqpack.utils.turbo_quant_rotation import get_rotation_matrix, inverse_rotate
from seqpack.utils.qjl import get_projection_matrix, qjl_decode
from seqpack.decoding.schemes.bm_decoding import decode as bm_decode


def decode(
    feature_value: list,
    tq_dim: int = 0,
    tq_bits: int = 4,
    tq_seed: int = 42,
    tq_norm: float = 1.0,
    tq_rnorm: float | None = None,
    tq_qseed: int | None = None,
    tq_signs: list | None = None,
) -> List[float]:
    """Decode a TurboQuant prod index list to a float list.

    Args:
        feature_value: List of integer MSE codebook indices from tbqp encode.
        tq_dim: Vector dimension (from aux).
        tq_bits: Total bits per coordinate (from aux).
        tq_seed: Rotation seed (from aux).
        tq_norm: Original vector norm (from aux).
        tq_rnorm: Residual norm (from aux).
        tq_qseed: QJL projection seed (from aux).
        tq_signs: QJL sign vector as a bm-encoded string (from aux).

    Returns:
        Reconstructed list of floats.
    """
    if not feature_value or tq_dim == 0:
        return []

    config = TurboQuantConfig(
        dimension=tq_dim, num_bits=tq_bits, seed=tq_seed, variant="prod",
        norm=tq_norm, residual_norm=tq_rnorm, qjl_seed=tq_qseed,
    )
    d = config.dimension
    mse_bits = config.num_bits - 1

    indices = np.asarray(feature_value, dtype=np.intp)
    codebook = get_codebook_array(mse_bits, d)
    y_reconstructed = dequantize_indices(indices, codebook)
    Pi = get_rotation_matrix(d, config.seed)
    x_mse = inverse_rotate(y_reconstructed, Pi)

    residual_norm = config.residual_norm or 0.0
    S = get_projection_matrix(d, config.qjl_seed or 43)
    if tq_signs:
        bits = bm_decode(tq_signs)
        signs = np.array([2 * b - 1 for b in bits], dtype=np.int8)
    else:
        signs = np.ones(d, dtype=np.int8)
    x_qjl = qjl_decode(signs, S, residual_norm)

    return ((x_mse + x_qjl) * config.norm).tolist()
