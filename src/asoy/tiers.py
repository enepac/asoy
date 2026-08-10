"""Hardware tier detection: GPU tier at 6 GB VRAM or more, CPU fallback (ARCHITECTURE section 5).

Detection runs once at startup (ARCHITECTURE section 4.2) and must never raise. Output quality
depends on the tier, so invariant 8 requires the active tier to be visible and explainable: every
result carries a reason string, including the failure paths.

**This deliberately does not use torch.cuda.is_available(), and must not be "simplified" back to
it.** That call reports whether the installed torch build was compiled with CUDA support, which is
a different question from whether the machine has a capable GPU. The two answers diverge in
practice: the torch wheel that resolves from PyPI on Windows is CPU-only, so an RTX 3050 with a
working driver reported no CUDA device and every user would have been pinned to the CPU tier
regardless of their hardware. NVML asks the driver directly, which is the question ADR-003 needs
answered. See ADR-021.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ARCHITECTURE section 5 states the GPU tier as "6 GB VRAM or more". This threshold is
# deliberately 5.5 GiB rather than a literal 6 GiB, and tightening it would be a regression.
#
# The nominal figure on a box and the figure a machine reports are not the same number, in two
# ways that both bite at exactly 6 GB. Vendors market capacity in decimal GB, so a card sold as
# "6 GB" can be 6,000,000,000 bytes, which is 5.59 GiB and below a binary 6 GiB threshold. And
# some cards report less than their nominal capacity once the driver or ECC has taken its share.
# The reference card, an RTX 3050 with a nominal 6144 MiB, happens to report the full
# 6,442,450,944 bytes through NVML, but that is the best case rather than the guaranteed one.
#
# 5.5 GiB absorbs both effects while staying far clear of any 4 GB card. Do not "tidy" this to a
# round 6 GiB: the failure is silent. Nothing errors, the user simply gets the CPU tier's weaker
# chart descriptions with no indication why. See test_tiers.py for the guard.
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


def _cpu(reason: str, name: str | None = None, total: int | None = None) -> TierDetection:
    return TierDetection(
        tier=Tier.CPU, device_name=name, total_vram_bytes=total, reason=reason
    )


def _device_name(raw: object) -> str:
    """NVML returns str on current bindings and bytes on older ones. Accept both."""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def detect() -> TierDetection:
    """Detect the active hardware tier. Never raises; any failure degrades to the CPU tier."""
    try:
        import pynvml
    except Exception as exc:
        return _cpu(
            f"The NVML binding could not be imported ({type(exc).__name__}: {exc}), "
            "so no GPU could be inspected. The CPU tier is active."
        )

    try:
        pynvml.nvmlInit()
    except Exception as exc:
        return _cpu(
            f"No NVIDIA driver is reachable through NVML ({type(exc).__name__}: {exc}). "
            "This is expected on a machine with no NVIDIA GPU. The CPU tier is active."
        )

    try:
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            return _cpu(
                "The NVIDIA driver is present but reports no devices, "
                "so the CPU tier is active."
            )

        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = _device_name(pynvml.nvmlDeviceGetName(handle))
        total = int(pynvml.nvmlDeviceGetMemoryInfo(handle).total)

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

        return _cpu(
            f"{name} reports {_gib(total)} of video memory, below the "
            f"{_gib(GPU_TIER_MIN_BYTES)} GPU tier threshold, so the CPU tier is active.",
            name=name,
            total=total,
        )
    except Exception as exc:
        return _cpu(
            f"Tier detection failed ({type(exc).__name__}: {exc}). "
            "Falling back to the CPU tier."
        )
    finally:
        # Always release the NVML handle. Detection runs on a path that can fail in several
        # places, and leaking a handle on each failure is a slow resource bug.
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
