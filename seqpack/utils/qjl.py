"""Quantized Johnson-Lindenstrauss (QJL) transform for TurboQuant.

QJL is a 1-bit inner product quantizer used in TurboQuant_prod to
provide unbiased inner product estimation on the residual vector.

Key properties:
- Q_qjl(x) = sign(S · x) where S is a random Gaussian matrix
- Q_qjl^{-1}(z) = (√(π/2) / d) · γ · S^T · z
- Provides unbiased inner product: E[⟨y, Q_qjl^{-1}(Q_qjl(x))⟩] = ⟨y, x⟩

Reference: TurboQuant paper Section 2.2 and Algorithm 2
"""

import numpy as np


def generate_projection_matrix(dimension: int, seed: int = 42) -> np.ndarray:
    """Generate random Gaussian projection matrix for QJL.
    
    Unlike the rotation matrix (which is orthogonal), this is a
    random matrix with i.i.d. N(0, 1) entries.
    
    Args:
        dimension: Size of the square matrix (d x d).
        seed: Random seed for reproducibility.
        
    Returns:
        Random Gaussian matrix S of shape (dimension, dimension).
    """
    rng = np.random.default_rng(seed)
    return rng.standard_normal((dimension, dimension))


# Simple dict cache for projection matrices (avoids slow tuple conversion)
_projection_matrix_cache: dict[tuple[int, int], np.ndarray] = {}


def get_projection_matrix(dimension: int, seed: int = 42) -> np.ndarray:
    """Get projection matrix as numpy array (with caching).
    
    Args:
        dimension: Matrix dimension.
        seed: Random seed.
        
    Returns:
        Projection matrix as numpy array.
    """
    key = (dimension, seed)
    if key not in _projection_matrix_cache:
        _projection_matrix_cache[key] = generate_projection_matrix(dimension, seed)
    return _projection_matrix_cache[key]


def qjl_encode(x: np.ndarray, projection_matrix: np.ndarray) -> np.ndarray:
    """Apply QJL encoding: sign(S · x).
    
    Quantizes each coordinate to 1 bit (+1 or -1).
    
    Args:
        x: Input vector of shape (d,) or batch of shape (n, d).
        projection_matrix: Random Gaussian matrix S of shape (d, d).
        
    Returns:
        Sign vector z ∈ {-1, +1}^d of same shape as input.
    """
    if x.ndim == 1:
        projected = projection_matrix @ x
    else:
        # Batch: x is (n, d), result is (n, d)
        projected = (projection_matrix @ x.T).T
    
    # Sign function: map to {-1, +1}
    # np.sign returns 0 for 0, so we handle that case
    signs = np.sign(projected)
    signs[signs == 0] = 1  # Map 0 to +1 (arbitrary but consistent)
    
    return signs.astype(np.int8)


def qjl_decode(
    z: np.ndarray,
    projection_matrix: np.ndarray,
    gamma: float,
) -> np.ndarray:
    """Apply QJL decoding: (√(π/2) / d) · γ · S^T · z.
    
    Args:
        z: Sign vector ∈ {-1, +1}^d of shape (d,) or batch (n, d).
        projection_matrix: Random Gaussian matrix S of shape (d, d).
        gamma: Norm of the original vector ||x||₂.
        
    Returns:
        Reconstructed vector of same shape as z.
    """
    d = projection_matrix.shape[0]
    scale = np.sqrt(np.pi / 2) / d * gamma
    
    if z.ndim == 1:
        return scale * (projection_matrix.T @ z.astype(np.float64))
    else:
        # Batch: z is (n, d), result is (n, d)
        return scale * (projection_matrix.T @ z.astype(np.float64).T).T


def qjl_encode_with_norm(
    x: np.ndarray,
    projection_matrix: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Encode vector and return both signs and norm.
    
    Convenience function that returns both the QJL encoding
    and the norm needed for decoding.
    
    Args:
        x: Input vector of shape (d,).
        projection_matrix: Random Gaussian matrix S.
        
    Returns:
        Tuple of (sign vector, norm ||x||₂).
    """
    gamma = float(np.linalg.norm(x))
    z = qjl_encode(x, projection_matrix)
    return z, gamma


def pack_signs_to_bytes(signs: np.ndarray) -> bytes:
    """Pack sign vector {-1, +1}^d into bytes.
    
    Maps -1 → 0, +1 → 1 and packs 8 bits per byte.
    
    Args:
        signs: Array of signs ∈ {-1, +1}.
        
    Returns:
        Packed bytes.
    """
    # Convert {-1, +1} to {0, 1}
    bits = ((signs + 1) // 2).astype(np.uint8)
    
    # Pad to multiple of 8
    padded_len = (len(bits) + 7) // 8 * 8
    if len(bits) < padded_len:
        bits = np.pad(bits, (0, padded_len - len(bits)))
    
    # Pack bits into bytes
    bits_reshaped = bits.reshape(-1, 8)
    weights = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint8)
    packed = (bits_reshaped * weights).sum(axis=1).astype(np.uint8)
    
    return packed.tobytes()


def unpack_bytes_to_signs(data: bytes, count: int) -> np.ndarray:
    """Unpack bytes back to sign vector.
    
    Args:
        data: Packed bytes.
        count: Number of signs to unpack.
        
    Returns:
        Array of signs ∈ {-1, +1}.
    """
    byte_arr = np.frombuffer(data, dtype=np.uint8)
    
    # Unpack each byte to 8 bits
    bits = np.unpackbits(byte_arr)[:count]
    
    # Convert {0, 1} back to {-1, +1}
    signs = bits.astype(np.int8) * 2 - 1
    
    return signs