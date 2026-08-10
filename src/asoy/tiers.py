"""Hardware tier detection: GPU tier at 6 GB VRAM or more, CPU fallback (ARCHITECTURE section 5).

Detection runs once at startup (ARCHITECTURE section 4.2) and must never raise. Output quality
depends on the tier, so invariant 8 requires the active tier to be visible and explainable: every
result carries a reason string, including the failure paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ARCHITECTURE section 5 states the GPU tier as "6 GB VRAM or more". This threshold is
# deliberately 5.5 GiB rather than a literal 6 GiB, and tightening it would be a regression.
#
# A card sold as 6 GB does not report 6 GiB to torch. The driver reserves a slice of the board
# before any application sees it, so torch's total_memory lands measurably below the nominal
# figure. The reference card is an RTX 3050 whose nominal capacity is 6144 MiB, which is exactly
# 6 GiB; the value torch reports for it is lower. Comparing against 6 * 1024**3 would therefore
# classify the exact card this tier was designed around as CPU.
#
# 5.5 GiB absorbs that reservation while staying far clear of any 4 GB card. Do not "tidy" this
# to a round 6 GiB: the failure is silent. Nothing errors, the user simply gets the CPU tier's
# weaker chart descriptions with no indication why. See test_tiers.py for the guard.
GPU_TIER_MIN_BYTES = int(5.5 * 1024**3)

_BYTES_PER_GIB = 1024**3


class Tier(StrEnum):
    """The two hardware tiers Asoy ships. No tier above GPU exists (ARCHITECTURE section 5)."""

    GPU = "GPU"
    CPU = "CPU"


@dataclass(frozen=True)
class TierDetection:
    """The outcome of one detection run, including why the tier was chosen."""

    tier: Tier
    device_name: str | None
    total_vram_bytes: int | None
    reason: str

    @property
    def total_vram_gib(self) -> float | None:
        """Total video memory in GiB, or None when no device was inspected."""
        if self.total_vram_bytes is None:
            return None
        return self.total_vram_bytes / _BYTES_PER_GIB


def _gib(value: int) -> str:
    return f"{value / _BYTES_PER_GIB:.2f} GiB"


def detect() -> TierDetection:
    """Detect the active hardware tier. Never raises; any failure degrades to the CPU tier."""
    try:
        import torch
    except Exception as exc:
        return TierDetection(
            tier=Tier.CPU,
            device_name=None,
            total_vram_bytes=None,
            reason=(
                f"Could not import torch ({type(exc).__name__}: {exc}). "
                "Falling back to the CPU tier."
            ),
        )

    try:
        if not torch.cuda.is_available():
            return TierDetection(
                tier=Tier.CPU,
                device_name=None,
                total_vram_bytes=None,
                reason=(
                    "No CUDA device is available to torch, so the CPU tier is active. "
                    "This is also what you see when a CUDA-capable card is present but the "
                    "installed torch build has no CUDA support."
                ),
            )

        properties = torch.cuda.get_device_properties(0)
        name = str(properties.name)
        total = int(properties.total_memory)

        if total >= GPU_TIER_MIN_BYTES:
            return TierDetection(
                tier=Tier.GPU,
                device_name=name,
                total_vram_bytes=total,
                reason=(
                    f"{name} reports {_gib(total)} of video memory, at or above the "
                    f"{_gib(GPU_TIER_MIN_BYTES)} GPU tier threshold."
                ),
            )

        return TierDetection(
            tier=Tier.CPU,
            device_name=name,
            total_vram_bytes=total,
            reason=(
                f"{name} reports {_gib(total)} of video memory, below the "
                f"{_gib(GPU_TIER_MIN_BYTES)} GPU tier threshold, so the CPU tier is active."
            ),
        )
    except Exception as exc:
        return TierDetection(
            tier=Tier.CPU,
            device_name=None,
            total_vram_bytes=None,
            reason=(
                f"Tier detection failed ({type(exc).__name__}: {exc}). "
                "Falling back to the CPU tier."
            ),
        )
