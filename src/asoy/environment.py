"""First-run environment check: is Ollama reachable, and is this tier's model pulled?

ARCHITECTURE section 6 requires this to run at every startup, not only the first, because users
uninstall things. ADR-008 makes Ollama a prerequisite rather than a bundled component, which is
the single largest source of setup friction in the product, so every failure here carries a
remedy the user can act on without searching (CLAUDE.md section 6).

The checks run in order and stop at the first failure. Note that reachability collapses
"installed" and "running" into one observable: over HTTP, a process that is installed but stopped
is indistinguishable from one that was never installed, so the message names both possibilities
rather than asserting either.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from asoy.tiers import Tier

DEFAULT_HOST = "http://127.0.0.1:11434"

# SUPPORT.md tells users that a non-default port is the usual cause of "unreachable", so the
# endpoint has to be overridable. OLLAMA_HOST is the variable Ollama itself uses.
HOST_ENV_VAR = "OLLAMA_HOST"

# A hung startup is worse than a reported failure, so this is deliberately short.
REQUEST_TIMEOUT_SECONDS = 3.0

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"

# UNVERIFIED TAGS. These strings have not been confirmed against the Ollama library, and they are
# the one place in the codebase where a model is named, so a wrong value here is a wrong value
# everywhere. They are a best reading of the models ARCHITECTURE section 5 specifies
# (Qwen3-VL-4B at Q4, and Moondream 2), not a checked fact.
#
# Confirm both against `ollama list` or the Ollama library before the first real conversion. If a
# tag is wrong the symptom is a "model not pulled" message that no amount of pulling fixes, since
# the user would be pulling a name that does not exist.
#
# CLAUDE.md section 5 lists model choice as ask-first. This mapping is the single place any such
# change happens; do not inline a tag anywhere else.
MODEL_TAGS: dict[Tier, str] = {
    Tier.GPU: "qwen3-vl:4b",
    Tier.CPU: "moondream:v2",
}


class EnvironmentStatus(StrEnum):
    """Why the environment is or is not ready. One value per distinguishable cause."""

    READY = "ready"
    OLLAMA_UNREACHABLE = "ollama_unreachable"
    MODEL_MISSING = "model_missing"
    OCR_WEIGHTS_MISSING = "ocr_weights_missing"
    CHECK_FAILED = "check_failed"


@dataclass(frozen=True)
class EnvironmentCheck:
    """The outcome of one environment check, including what to do about it."""

    ok: bool
    status: EnvironmentStatus
    detail: str
    remedy: str


def resolve_host() -> str:
    """The Ollama endpoint, from the environment if set, otherwise the standard local address."""
    return os.environ.get(HOST_ENV_VAR) or DEFAULT_HOST


def model_tag_for(tier: Tier) -> str:
    """The model tag this tier requires. See the note on MODEL_TAGS before changing anything."""
    return MODEL_TAGS[tier]


def _normalise(tag: str) -> str:
    """Ollama treats a bare name as ':latest'. Compare like for like."""
    return tag if ":" in tag else f"{tag}:latest"


def _is_connection_problem(exc: BaseException) -> bool:
    """True when the exception means we could not reach Ollama, rather than could not parse it."""
    if isinstance(exc, ConnectionError | TimeoutError | OSError):
        return True
    name = type(exc).__name__
    return "Connect" in name or "Timeout" in name


def _unreachable(host: str, cause: str) -> EnvironmentCheck:
    return EnvironmentCheck(
        ok=False,
        status=EnvironmentStatus.OLLAMA_UNREACHABLE,
        detail=(
            f"Could not reach Ollama at {host} ({cause}). Either Ollama is not running, or it is "
            "not installed. Over HTTP these look the same, so both are worth checking."
        ),
        remedy=(
            f"Install Ollama from {OLLAMA_DOWNLOAD_URL} if you have not already, then start it. "
            f"On Windows it runs in the background once installed. If it is already running on a "
            f"non-default port, set {HOST_ENV_VAR} to that address, for example "
            f'{HOST_ENV_VAR}="http://127.0.0.1:11434".'
        ),
    )


def check(tier: Tier) -> EnvironmentCheck:
    """Check the environment for the given tier. Never raises; failures come back as results."""
    host = resolve_host()

    try:
        tag = model_tag_for(tier)
    except Exception as exc:
        return EnvironmentCheck(
            ok=False,
            status=EnvironmentStatus.CHECK_FAILED,
            detail=f"No model is mapped for the {tier} tier ({type(exc).__name__}: {exc}).",
            remedy="This is a defect in Asoy, not something you can fix. Please report it.",
        )

    try:
        import ollama
    except Exception as exc:
        return EnvironmentCheck(
            ok=False,
            status=EnvironmentStatus.CHECK_FAILED,
            detail=(
                f"The Ollama client library could not be imported "
                f"({type(exc).__name__}: {exc})."
            ),
            remedy="Reinstall Asoy. This indicates a damaged installation, not a setup mistake.",
        )

    try:
        client = ollama.Client(host=host, timeout=REQUEST_TIMEOUT_SECONDS)
        response = client.list()
    except Exception as exc:
        if _is_connection_problem(exc):
            return _unreachable(host, f"{type(exc).__name__}: {exc}")
        return EnvironmentCheck(
            ok=False,
            status=EnvironmentStatus.CHECK_FAILED,
            detail=f"Asking Ollama for its model list failed ({type(exc).__name__}: {exc}).",
            remedy=(
                f"Check that Ollama at {host} is healthy, for example by running 'ollama list' "
                "in a terminal. If that works and Asoy still fails, please report it."
            ),
        )

    try:
        installed = {_normalise(str(entry.model)) for entry in response.models}
    except Exception as exc:
        return EnvironmentCheck(
            ok=False,
            status=EnvironmentStatus.CHECK_FAILED,
            detail=(
                f"Ollama replied at {host}, but its model list could not be read "
                f"({type(exc).__name__}: {exc})."
            ),
            remedy=(
                "This usually means a version mismatch between Ollama and Asoy. Update Ollama, "
                "then try again. If it persists, please report it."
            ),
        )

    if _normalise(tag) not in installed:
        return EnvironmentCheck(
            ok=False,
            status=EnvironmentStatus.MODEL_MISSING,
            detail=(
                f"Ollama is running at {host}, but the {tier} tier needs the model {tag}, "
                "which has not been pulled."
            ),
            remedy=f"ollama pull {tag}",
        )

    # The OCR weights are the second thing that must be in place, and unlike Ollama they are
    # needed only for scanned input (ADR-029). They are reported last so that a user who converts
    # only EPUBs sees the reason they are listed rather than a bare failure.
    from asoy.ocr import FETCH_COMMAND, REQUIRED_WEIGHTS
    from asoy.ocr import status as ocr_status

    weights = ocr_status()
    if not weights.ready:
        return EnvironmentCheck(
            ok=False,
            status=EnvironmentStatus.OCR_WEIGHTS_MISSING,
            detail=(
                f"Ollama is ready. The OCR models are not: {len(weights.missing)} of "
                f"{len(REQUIRED_WEIGHTS)} are missing from {weights.directory}. Scanned PDFs and "
                "images need them; EPUB, DOCX, and ODT do not."
            ),
            remedy=(
                f"Run '{FETCH_COMMAND}' once. Asoy never downloads them during a conversion, so "
                "that converting a book makes no network request at all."
            ),
        )

    return EnvironmentCheck(
        ok=True,
        status=EnvironmentStatus.READY,
        detail=(
            f"Ollama is reachable at {host}, the {tier} tier model {tag} is available, and the "
            f"OCR models are present in {weights.directory}."
        ),
        remedy="",
    )
