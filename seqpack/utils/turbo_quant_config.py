"""Shared TurboQuantConfig dataclass used by both tbqm and tbqp schemes."""

from dataclasses import dataclass
from typing import Any


@dataclass
class TurboQuantConfig:
    """Configuration for TurboQuant encoding/decoding.

    Attributes:
        dimension: Vector dimension d (must be >= 3 for codebook generation).
        num_bits: Bits per coordinate for quantization.
        seed: Random seed for rotation matrix.
        variant: 'mse' or 'prod'.
        norm: Original vector norm for denormalization.
        residual_norm: Norm of residual vector (prod variant only).
        qjl_seed: Seed for QJL projection matrix (prod variant only).
    """
    dimension: int
    num_bits: int
    seed: int
    variant: str = "mse"
    norm: float = 1.0
    residual_norm: float | None = None
    qjl_seed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tq_dim": self.dimension,
            "tq_bits": self.num_bits,
            "tq_seed": self.seed,
            "tq_norm": self.norm,
            "tq_rnorm": self.residual_norm,
            "tq_qseed": self.qjl_seed,
        }

    @classmethod
    def from_aux(cls, variant: str, **kwargs) -> "TurboQuantConfig":
        return cls(
            dimension=int(kwargs.get("tq_dim", 0)),
            num_bits=int(kwargs.get("tq_bits", 4)),
            seed=int(kwargs.get("tq_seed", 42)),
            variant=variant,
            norm=float(kwargs.get("tq_norm", 1.0)),
            residual_norm=kwargs.get("tq_rnorm"),
            qjl_seed=kwargs.get("tq_qseed"),
        )
