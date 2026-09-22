"""Lloyd-Max optimal codebook generation for TurboQuant.

This module generates and caches optimal scalar quantization codebooks
using the Lloyd-Max algorithm for the exact Beta distribution.

After random rotation, each coordinate of a unit-norm vector follows:
    f(x) = Gamma(d/2) / (sqrt(pi) * Gamma((d-1)/2)) * (1 - x^2)^((d-3)/2)

This is a scaled Beta distribution on [-1, 1]. For high d, it converges to N(0, 1/d).

Reference: TurboQuant paper (arXiv:2504.19874)
Reference implementation: https://github.com/0xSero/turboquant
"""

import json
import os
import pathlib

import numpy as np
from scipy import special, integrate

_CODEBOOK_DISK_CACHE_PATH = pathlib.Path(
    os.environ.get(
        "TURBO_QUANT_CODEBOOK_CACHE",
        pathlib.Path(__file__).parent / "_codebook_cache.json",
    )
)


def beta_pdf(x: np.ndarray, d: int) -> np.ndarray:
    """PDF of a single coordinate of a uniform random point on S^{d-1}.
    
    After random rotation, each coordinate follows this distribution
    on the interval [-1, 1].
    
    Args:
        x: Points at which to evaluate the PDF.
        d: Dimension of the embedding space.
        
    Returns:
        PDF values at the given points.
    """
    if d < 3:
        raise ValueError(f"Dimension d={d} too small, need d >= 3")
    
    # Log of normalization constant: Gamma(d/2) / (sqrt(pi) * Gamma((d-1)/2))
    log_const = (
        special.gammaln(d / 2.0)
        - 0.5 * np.log(np.pi)
        - special.gammaln((d - 1) / 2.0)
    )
    exponent = (d - 3) / 2.0
    
    # Clip x to avoid numerical issues at boundaries
    x = np.clip(x, -1 + 1e-15, 1 - 1e-15)
    log_val = log_const + exponent * np.log(1 - x**2)
    return np.exp(log_val)


def _beta_conditional_mean(lo: float, hi: float, d: int) -> float:
    """Compute E[X | lo < X < hi] under the Beta PDF on [-1, 1].
    
    Uses numerical integration.
    
    Args:
        lo: Lower bound of the interval.
        hi: Upper bound of the interval.
        d: Dimension.
        
    Returns:
        Conditional expectation E[X | lo < X < hi].
    """
    # Numerator: integral of x * pdf(x)
    num, _ = integrate.quad(
        lambda x: x * beta_pdf(np.array([x]), d)[0], lo, hi
    )
    # Denominator: integral of pdf(x)
    den, _ = integrate.quad(
        lambda x: beta_pdf(np.array([x]), d)[0], lo, hi
    )
    
    if den < 1e-30:
        return (lo + hi) / 2.0
    return num / den


def _mse_cost(centroids: np.ndarray, d: int) -> float:
    """Compute MSE cost for a given set of sorted centroids.
    
    Args:
        centroids: Array of centroid values.
        d: Dimension.
        
    Returns:
        Total MSE cost.
    """
    n = len(centroids)
    boundaries = np.zeros(n + 1)
    boundaries[0] = -1.0
    boundaries[-1] = 1.0
    for i in range(n - 1):
        boundaries[i + 1] = (centroids[i] + centroids[i + 1]) / 2.0
    
    cost = 0.0
    for i in range(n):
        lo, hi = boundaries[i], boundaries[i + 1]
        c = centroids[i]
        val, _ = integrate.quad(
            lambda x: (x - c) ** 2 * beta_pdf(np.array([x]), d)[0], lo, hi
        )
        cost += val
    return cost


def compute_lloyd_max_codebook(
    d: int,
    num_bits: int,
    max_iterations: int = 200,
    tolerance: float = 1e-12,
) -> dict:
    """Compute Lloyd-Max optimal codebook for the Beta distribution on [-1, 1].
    
    The Lloyd-Max algorithm iteratively finds optimal quantization centroids
    that minimize mean squared error for the distribution arising from
    random rotation of d-dimensional unit vectors.

    Swapnil - Naive implementation was simple following guassian distribution N(0, 1/sqrt(d)) which 
    was removed to include beta distribution to follow paper strictly.
    
    Args:
        d: Dimension of the embedding space (e.g., head_dim = 128).
        num_bits: Number of bits for quantization (1-8). Codebook size = 2^num_bits.
        max_iterations: Maximum number of Lloyd-Max iterations.
        tolerance: Convergence tolerance.
        
    Returns:
        Dict with keys:
            'centroids': sorted array of 2^num_bits centroids
            'boundaries': sorted array of 2^num_bits + 1 boundaries
            'mse_per_coord': achieved MSE cost per coordinate
            'd': dimension
            'bits': bit-width
        
    Example:
        >>> result = compute_lloyd_max_codebook(128, 2)
        >>> len(result['centroids'])
        4
    """
    if num_bits < 1 or num_bits > 8:
        raise ValueError("num_bits must be between 1 and 8")
    if d < 3:
        raise ValueError("dimension must be >= 3")
    
    num_levels = 2 ** num_bits
    
    # Initialize centroids using quantiles of the Beta distribution
    # Approximate CDF via numerical integration
    x_grid = np.linspace(-1 + 1e-10, 1 - 1e-10, 10000)
    pdf_vals = beta_pdf(x_grid, d)
    cdf_vals = np.cumsum(pdf_vals) * (x_grid[1] - x_grid[0])
    cdf_vals /= cdf_vals[-1]  # Normalize to [0, 1]
    
    # Place initial centroids at quantile midpoints
    quantile_edges = np.linspace(0, 1, num_levels + 1)
    centroids = np.zeros(num_levels)
    for i in range(num_levels):
        q_mid = (quantile_edges[i] + quantile_edges[i + 1]) / 2.0
        idx = np.searchsorted(cdf_vals, q_mid)
        idx = min(idx, len(x_grid) - 1)
        centroids[i] = x_grid[idx]
    
    # Lloyd-Max iteration
    prev_cost = float("inf")
    for iteration in range(max_iterations):
        # Compute decision boundaries (midpoints between adjacent centroids)
        boundaries = np.zeros(num_levels + 1)
        boundaries[0] = -1.0
        boundaries[-1] = 1.0
        for i in range(num_levels - 1):
            boundaries[i + 1] = (centroids[i] + centroids[i + 1]) / 2.0
        
        # Update centroids to conditional means within each partition
        new_centroids = np.zeros(num_levels)
        for i in range(num_levels):
            new_centroids[i] = _beta_conditional_mean(
                boundaries[i], boundaries[i + 1], d
            )
        
        # Compute MSE cost
        cost = _mse_cost(new_centroids, d)
        centroids = new_centroids
        
        # Check convergence
        if abs(prev_cost - cost) < tolerance:
            break
        prev_cost = cost
    
    # Recompute final boundaries
    boundaries = np.zeros(num_levels + 1)
    boundaries[0] = -1.0
    boundaries[-1] = 1.0
    for i in range(num_levels - 1):
        boundaries[i + 1] = (centroids[i] + centroids[i + 1]) / 2.0
    
    return {
        "centroids": centroids.tolist(),
        "boundaries": boundaries.tolist(),
        "mse_per_coord": float(cost),
        "d": d,
        "bits": num_bits,
    }


def compute_codebook_for_dimension(num_bits: int, dimension: int) -> np.ndarray:
    """Compute codebook for TurboQuant with specific dimension.
    
    After random rotation, each coordinate of a unit vector follows
    the Beta distribution on [-1, 1].
    
    Args:
        num_bits: Number of bits for quantization.
        dimension: Vector dimension d.
        
    Returns:
        Optimal codebook centroids as numpy array.
    """
    result = compute_lloyd_max_codebook(dimension, num_bits)
    return np.array(result["centroids"])


# Simple dict cache for codebooks (avoids lru_cache tuple conversion overhead)
_codebook_cache: dict[tuple[int, int], dict] = {}

# Load persisted codebooks from disk on first import.
def _load_disk_cache() -> None:
    if not _CODEBOOK_DISK_CACHE_PATH.exists():
        return
    try:
        raw = json.loads(_CODEBOOK_DISK_CACHE_PATH.read_text())
        for key_str, entry in raw.items():
            bits, dim = map(int, key_str.split(","))
            _codebook_cache[(bits, dim)] = entry
    except Exception:
        pass

_load_disk_cache()


def _save_disk_cache() -> None:
    try:
        serializable = {f"{k[0]},{k[1]}": v for k, v in _codebook_cache.items()}
        _CODEBOOK_DISK_CACHE_PATH.write_text(json.dumps(serializable))
    except Exception:
        pass


def get_codebook(num_bits: int, dimension: int) -> dict:
    """Get codebook for given parameters (cached).
    
    Args:
        num_bits: Number of bits for quantization.
        dimension: Vector dimension.
        
    Returns:
        Dict with 'centroids', 'boundaries', 'mse_per_coord', 'd', 'bits'.
    """
    key = (num_bits, dimension)
    if key not in _codebook_cache:
        _codebook_cache[key] = compute_lloyd_max_codebook(dimension, num_bits)
        _save_disk_cache()
    return _codebook_cache[key]


def get_codebook_array(num_bits: int, dimension: int) -> np.ndarray:
    """Get codebook as numpy array (uses cached computation).
    
    Args:
        num_bits: Number of bits for quantization.
        dimension: Vector dimension.
        
    Returns:
        NumPy array of codebook centroids.
    """
    cb = get_codebook(num_bits, dimension)
    return np.array(cb["centroids"])


def quantize_scalar(value: float, codebook: np.ndarray) -> int:
    """Quantize a single scalar value to nearest codebook index.
    
    Args:
        value: Scalar value to quantize.
        codebook: Array of codebook centroids.
        
    Returns:
        Index of nearest centroid.
    """
    return int(np.argmin(np.abs(codebook - value)))


def quantize_vector(values: np.ndarray, codebook: np.ndarray) -> np.ndarray:
    """Quantize a vector to nearest codebook indices (vectorized).
    
    Args:
        values: Array of values to quantize.
        codebook: Array of codebook centroids.
        
    Returns:
        Array of indices (dtype=int).
    """
    # Compute distances to all centroids: shape (len(values), len(codebook))
    distances = np.abs(values[:, np.newaxis] - codebook)
    return np.argmin(distances, axis=1)


def dequantize_indices(indices: np.ndarray, codebook: np.ndarray) -> np.ndarray:
    """Convert indices back to centroid values.
    
    Args:
        indices: Array of codebook indices.
        codebook: Array of codebook centroids.
        
    Returns:
        Array of centroid values.
    """
    return codebook[indices]


def compute_quantization_mse(
    values: np.ndarray,
    codebook: np.ndarray,
) -> float:
    """Compute MSE for quantizing values with given codebook.
    
    Args:
        values: Original values.
        codebook: Codebook to use for quantization.
        
    Returns:
        Mean squared error.
    """
    indices = quantize_vector(values, codebook)
    reconstructed = dequantize_indices(indices, codebook)
    return float(np.mean((values - reconstructed) ** 2))