"""Random rotation matrix utilities for TurboQuant.

This module provides functions to generate and apply random orthogonal
rotation matrices used in TurboQuant for transforming input vectors.

The key insight from TurboQuant is that applying a random rotation to
a unit-norm vector induces a Beta distribution on each coordinate,
which concentrates to Gaussian N(0, 1/d) in high dimensions.
"""

import math
import numpy as np


# =============================================================================
# Platform-Independent PCG64 Implementation
# =============================================================================
# PCG64 (Permuted Congruential Generator) is a high-quality PRNG.
# This implementation is deterministic and platform-independent.
# Reference: https://www.pcg-random.org/

class PCG64:
    """Platform-independent PCG64 random number generator.
    
    This implementation produces identical output across:
    - Different Python versions
    - Different NumPy versions  
    - Different CPU architectures (x86, ARM, etc.)
    - Different operating systems
    
    Uses PCG-XSL-RR variant with 128-bit state and 64-bit output.
    """
    
    # PCG64 constants
    MULTIPLIER = 6364136223846793005
    INCREMENT = 1442695040888963407  # Must be odd
    MASK64 = (1 << 64) - 1
    MASK128 = (1 << 128) - 1
    
    def __init__(self, seed: int = 42):
        """Initialize PCG64 with a seed.
        
        Args:
            seed: Integer seed for reproducibility.
        """
        # Initialize 128-bit state from seed
        # Use a simple but deterministic initialization
        self._state = ((seed ^ self.MULTIPLIER) * self.MULTIPLIER + self.INCREMENT) & self.MASK128
        # Advance state once to mix
        self._advance()
    
    def _advance(self) -> None:
        """Advance the internal state by one step."""
        self._state = (self._state * self.MULTIPLIER + self.INCREMENT) & self.MASK128
    
    def _output(self) -> int:
        """Generate 64-bit output from current state using XSL-RR permutation."""
        # XSL-RR: XOR high and low 64 bits, then rotate
        state = self._state
        high = (state >> 64) & self.MASK64
        low = state & self.MASK64
        xored = high ^ low
        
        # Rotation amount from high bits
        rot = (state >> 122) & 63
        
        # Rotate right
        return ((xored >> rot) | (xored << (64 - rot))) & self.MASK64
    
    def random_uint64(self) -> int:
        """Generate a random 64-bit unsigned integer."""
        result = self._output()
        self._advance()
        return result
    
    def random_float64(self) -> float:
        """Generate a random float in [0, 1) with 53-bit precision."""
        # Use 53 bits for IEEE 754 double precision mantissa
        return (self.random_uint64() >> 11) / (1 << 53)
    
    def random_gaussian(self) -> float:
        """Generate a standard normal random number using Box-Muller transform.
        
        Returns:
            A sample from N(0, 1).
        """
        # Box-Muller transform: generates two independent N(0,1) samples
        # We only use one per call for simplicity
        while True:
            u1 = self.random_float64()
            u2 = self.random_float64()
            if u1 > 1e-15:  # Avoid log(0)
                break
        
        # Box-Muller formula
        mag = math.sqrt(-2.0 * math.log(u1))
        z0 = mag * math.cos(2.0 * math.pi * u2)
        return z0
    
    def random_gaussian_array(self, shape: tuple) -> np.ndarray:
        """Generate array of standard normal random numbers.

        Args:
            shape: Shape of output array.

        Returns:
            NumPy array of N(0, 1) samples.
        """
        size = 1
        for dim in shape:
            size *= dim

        # Box-Muller needs pairs: ceil(size/2) pairs → n uint64s.
        n_pairs = (size + 1) // 2
        n = n_pairs * 2

        # Vectorize the PCG64 state walk via numpy uint64 arithmetic.
        # State is 128-bit: split as state = (state_hi << 64) | state_lo.
        # Recurrence: state = state * MUL + INC  (mod 2^128).
        # We unroll n steps by computing MUL^n and INC accumulator.
        # But the simplest approach: generate the n sequential states
        # by broadcasting a starting state forward using the scalar loop
        # only once per 64-wide chunk, then vectorize the output permutation.
        #
        # Fastest practical approach without 128-bit numpy: compute all n
        # states' output words by pre-computing each state via the recurrence
        # in Python, but store results as numpy and do all output permutation
        # vectorized. This keeps the Python loop at n iters (unavoidable for
        # a sequential 128-bit PRNG) but eliminates all per-sample Python
        # arithmetic after the loop.
        states = np.empty(n, dtype=object)  # Python ints for 128-bit
        s = self._state
        M = self.MULTIPLIER
        I = self.INCREMENT
        MASK128 = self.MASK128
        MASK64 = self.MASK64
        for i in range(n):
            states[i] = s
            s = (s * M + I) & MASK128
        self._state = s  # advance past all generated samples

        # Vectorized XSL-RR output function over the array of Python-int states.
        # Extract high/low 64-bit words.
        high = np.array([(int(x) >> 64) & MASK64 for x in states], dtype=np.uint64)
        low  = np.array([int(x) & MASK64           for x in states], dtype=np.uint64)
        xored = high ^ low
        rot = (high >> np.uint64(58)).astype(np.uint64) & np.uint64(63)

        # Vectorized variable-rotation-right: (xored >> rot) | (xored << (64-rot))
        rot64 = np.uint64(64)
        uint64s = np.where(
            rot == np.uint64(0),
            xored,
            (xored >> rot) | (xored << (rot64 - rot)),
        ).astype(np.uint64)

        # Convert to float in [0, 1) with 53-bit precision
        floats = (uint64s >> np.uint64(11)).astype(np.float64) / float(1 << 53)

        # Box-Muller on consecutive pairs — each pair yields z0 and z1
        u1 = np.clip(floats[0::2], 1e-15, None)
        u2 = floats[1::2]
        mag = np.sqrt(-2.0 * np.log(u1))
        z0 = mag * np.cos(2.0 * np.pi * u2)
        z1 = mag * np.sin(2.0 * np.pi * u2)

        # Interleave z0 and z1 to get size samples
        result = np.empty(n, dtype=np.float64)
        result[0::2] = z0
        result[1::2] = z1

        return result[:size].reshape(shape)


def generate_rotation_matrix_unstable(dimension: int, seed: int = 42) -> np.ndarray:
    """
    
    !!!! UNSTABLE DUE TO HARD DEPENDNECY ON NUMPY VERSIONS, CPU/GPU ARCHITECTURES!!!!
    Generate a random orthogonal rotation matrix.
    
    Uses QR decomposition of a random Gaussian matrix to produce
    a uniformly distributed random orthogonal matrix.

    This is a well-known result: if you take a matrix with i.i.d. Gaussian entries and
    compute its QR decomposition, the Q matrix is uniformly distributed over all orthogonal
    matrices (Haar measure). This gives us a "truly random" rotation.
    
    The rotation "scrambles" the coordinates while preserving geometry, 
    making the quantization problem easier because we know the distribution of the scrambled 
    coordinates.
    
    Args:
        dimension: Size of the square rotation matrix (d x d).
        seed: Random seed for reproducibility.
        
    Returns:
        Orthogonal matrix Π of shape (dimension, dimension).
        
    Example:
        >>> Pi = generate_rotation_matrix(128, seed=42)
        >>> Pi.shape
        (128, 128)
        >>> np.allclose(Pi @ Pi.T, np.eye(128))  # Orthogonal check
        True
    """
    rng = np.random.default_rng(seed)
    
    # Generate random Gaussian matrix
    random_matrix = rng.standard_normal((dimension, dimension))
    
    # QR decomposition gives orthogonal Q
    Q, R = np.linalg.qr(random_matrix)
    
    # Ensure proper rotation (det = +1) by adjusting signs
    # This makes the rotation matrix unique given the seed
    signs = np.sign(np.diag(R))
    signs[signs == 0] = 1
    Q = Q * signs
    
    return Q

def generate_rotation_matrix(dimension: int, seed: int = 42) -> np.ndarray:
    """Generate a random orthogonal rotation matrix (platform-independent).
    
    Uses QR decomposition of a random Gaussian matrix to produce
    a uniformly distributed random orthogonal matrix.

    This implementation uses a custom PCG64 RNG that is deterministic and
    platform-independent, producing identical results across:
    - Different Python versions
    - Different NumPy versions
    - Different CPU architectures (x86, ARM, etc.)
    - Different operating systems
    
    Args:
        dimension: Size of the square rotation matrix (d x d).
        seed: Random seed for reproducibility.
        
    Returns:
        Orthogonal matrix Π of shape (dimension, dimension).
        
    Example:
        >>> Pi = generate_rotation_matrix(128, seed=42)
        >>> Pi.shape
        (128, 128)
        >>> np.allclose(Pi @ Pi.T, np.eye(128))  # Orthogonal check
        True
    """
    # Use platform-independent PCG64 RNG
    rng = PCG64(seed)
    
    # Generate random Gaussian matrix
    random_matrix = rng.random_gaussian_array((dimension, dimension))
    
    # QR decomposition gives orthogonal Q
    Q, R = np.linalg.qr(random_matrix)
    
    # Ensure proper rotation (det = +1) by adjusting signs
    # This makes the rotation matrix unique given the seed
    signs = np.sign(np.diag(R))
    signs[signs == 0] = 1
    Q = Q * signs
    
    return Q

#TODO - Generate rotation matrix using FWHT (Fast Walsh-Hadamard Transform) algorithm


# Simple dict cache for rotation matrices (avoids slow tuple conversion)
_rotation_matrix_cache: dict[tuple[int, int], np.ndarray] = {}


def get_rotation_matrix(dimension: int, seed: int = 42) -> np.ndarray:
    """Get rotation matrix as numpy array (with caching).
    
    Args:
        dimension: Matrix dimension.
        seed: Random seed.
        
    Returns:
        Rotation matrix as numpy array.
    """
    key = (dimension, seed)
    if key not in _rotation_matrix_cache:
        _rotation_matrix_cache[key] = generate_rotation_matrix(dimension, seed)
    return _rotation_matrix_cache[key]


def rotate(x: np.ndarray, rotation_matrix: np.ndarray) -> np.ndarray:
    """Apply rotation to vector(s).
    
    Computes y = Π · x for single vector or batch.
    
    Args:
        x: Input vector of shape (d,) or batch of shape (n, d).
        rotation_matrix: Orthogonal matrix Π of shape (d, d).
        
    Returns:
        Rotated vector(s) of same shape as input.
    """
    if x.ndim == 1:
        return rotation_matrix @ x
    else:
        # Batch: x is (n, d), result is (n, d)
        return (rotation_matrix @ x.T).T


def inverse_rotate(y: np.ndarray, rotation_matrix: np.ndarray) -> np.ndarray:
    """Apply inverse rotation to vector(s).
    
    Computes x = Π^T · y (since Π is orthogonal, Π^{-1} = Π^T).
    
    Args:
        y: Rotated vector of shape (d,) or batch of shape (n, d).
        rotation_matrix: Orthogonal matrix Π of shape (d, d).
        
    Returns:
        Original vector(s) of same shape as input.
    """
    if y.ndim == 1:
        return rotation_matrix.T @ y
    else:
        # Batch: y is (n, d), result is (n, d)
        return (rotation_matrix.T @ y.T).T


def verify_orthogonal(matrix: np.ndarray, tolerance: float = 1e-10) -> bool:
    """Verify that a matrix is orthogonal.
    
    Args:
        matrix: Square matrix to check.
        tolerance: Numerical tolerance for comparison.
        
    Returns:
        True if matrix is orthogonal (Π · Π^T ≈ I).
    """
    identity = np.eye(matrix.shape[0])
    product = matrix @ matrix.T
    return np.allclose(product, identity, atol=tolerance)


def verify_rotation_preserves_norm(
    x: np.ndarray,
    rotation_matrix: np.ndarray,
    tolerance: float = 1e-10,
) -> bool:
    """Verify that rotation preserves vector norm.
    
    Args:
        x: Input vector.
        rotation_matrix: Rotation matrix.
        tolerance: Numerical tolerance.
        
    Returns:
        True if ||Π·x|| ≈ ||x||.
    """
    y = rotate(x, rotation_matrix)
    return np.abs(np.linalg.norm(x) - np.linalg.norm(y)) < tolerance