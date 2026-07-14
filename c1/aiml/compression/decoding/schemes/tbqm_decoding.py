"""TurboQuant MSE decoder — scheme code `tbqm`.

Reconstructs a float vector from TurboQuant_MSE encoded data:
  1. Look up centroid values for the codebook indices.
  2. Inverse-rotate to recover the normalized vector.
  3. Denormalize by the stored norm.
"""

from typing import List

import numpy as np

from c1.aiml.compression.utils.turbo_quant_config import TurboQuantConfig
from c1.aiml.compression.utils.turbo_quant_codebook import get_codebook_array, dequantize_indices
from c1.aiml.compression.utils.turbo_quant_rotation import get_rotation_matrix, inverse_rotate


def decode(
    feature_value: list,
    tq_dim: int = 0,
    tq_bits: int = 4,
    tq_seed: int = 42,
    tq_norm: float = 1.0,
) -> List[float]:
    """Decode a TurboQuant MSE index list to a float list.

    Args:
        feature_value: List of integer codebook indices from tbqm encode.
        tq_dim: Vector dimension (from aux).
        tq_bits: Bits per coordinate (from aux).
        tq_seed: Rotation seed (from aux).
        tq_norm: Original vector norm (from aux).

    Returns:
        Reconstructed list of floats.
    """
    if not feature_value or tq_dim == 0:
        return []

    config = TurboQuantConfig(
        dimension=tq_dim, num_bits=tq_bits, seed=tq_seed, variant="mse", norm=tq_norm
    )
    d = config.dimension

    indices = np.asarray(feature_value, dtype=np.intp)
    codebook = get_codebook_array(config.num_bits, d)
    y_reconstructed = dequantize_indices(indices, codebook)

    Pi = get_rotation_matrix(d, config.seed)
    x_normalized = inverse_rotate(y_reconstructed, Pi)

    return (x_normalized * config.norm).tolist()
