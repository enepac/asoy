"""Block Classifier: assigns a picture block its type (ARCHITECTURE section 4.6, ADR-026).

The type selects the description prompt, which is why this component exists at all: a table read
aloud, a chart explained by what it shows, and a photograph described by what is depicted are
three different jobs, and one generic prompt for all of them is noticeably worse.

**Tables never reach here.** The parser types them from their own structure and carries their
cells (section 4.6), so this module sees pictures only.

Two stages, cheapest first (ADR-026):

1. A caption pre-pass. Books usually say what their pictures are, and reading the caption costs
   nothing next to a vision model call.
2. For anything the caption did not settle, one call to the tier's existing vision model —
   qwen3-vl:4b on the GPU tier, moondream:v2 on the CPU tier. No new model and no new dependency.

**`unknown` is an answer, not a failure.** Below the certainty floor the block keeps `unknown`
rather than taking the model's best guess. A wrong type selects a wrong description prompt, which
produces confident prose about the wrong kind of thing; an honest `unknown` gets generic handling
that is merely unremarkable. The floor is the knob that trades those against each other, and it
has not been set against evidence yet — see the note on CERTAINTY below.

Invariant 1 holds: the only request this module makes is to Ollama on the local address resolved
by `asoy.environment`. Invariant 8 holds: every result carries the tier and model it ran under,
because the tier selects the model and therefore the answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from asoy.classifier.prepass import read_caption
from asoy.classifier.prompt import CLASSIFIABLE_TYPES, RESPONSE_SCHEMA, build_prompt
from asoy.environment import model_tag_for, resolve_host
from asoy.fences import DescriptionType
from asoy.tiers import Tier

# A vision model on the CPU tier can take a long time over one image, and a book has many. This
# is a ceiling on a hung request rather than a target: exceeding it yields `unknown` for that
# block, which the job survives.
REQUEST_TIMEOUT_SECONDS = 180.0

# Below this, the answer is discarded and the block stays `unknown`.
#
# UNVALIDATED. This number decides the trade the module docstring describes, and it is the first
# thing to tune once `reference/classifier/` exists — it moves the measured `unknown` rate almost
# directly. It is not a considered value; it is a placeholder chosen to be mildly conservative.
CERTAINTY_FLOOR = 0.60


class Evidence(StrEnum):
    """What the answer rests on. Recorded so a wrong type names its own cause."""

    CAPTION = "caption"
    MODEL = "model"
    NONE = "none"


# Certainty by evidence. Two properties matter more than the exact numbers.
#
# It is on the same 0.00 to 1.00 scale as the description fence's `confidence` attribute
# (ARCHITECTURE 4.8), because that is where it ends up: the fence's confidence combines the
# description's own signal with the classification certainty, and two scales would have to be
# reconciled at the point of emission by whoever writes that code next.
#
# And it is derived from named evidence rather than from a model's opinion of itself. A caption
# that says "photograph" is a fact about the book; a model's self-reported certainty is not
# calibrated against anything (ADR-025 says the same of the fence attribute). The caption value
# sits above anything the model can claim for that reason.
CAPTION_CERTAINTY = 0.90

# The model's self-report is clamped into this band before use. The ceiling denies it the
# certainty a caption earns; the floor keeps a model that reports 0.0 from being distinguishable
# from a failed call, which is a different thing and is recorded differently.
MODEL_CERTAINTY_CEILING = 0.80
MODEL_CERTAINTY_FLOOR = 0.05


@dataclass(frozen=True)
class PictureBlock:
    """One picture to classify, as the parser would hand it over.

    `image` is the encoded picture as bytes, in whatever format it was embedded — Ollama accepts
    the common ones and does its own decoding. `caption` is the block's own caption; `context` is
    nearby prose, which the pre-pass does not read and the model call receives.

    This is not yet produced anywhere. The classifier lands with its measurement harness rather
    than with a consumer, so the parser is unchanged and wiring is a later commit.
    """

    image: bytes
    caption: str = ""
    context: str = ""
    locator: str = ""


@dataclass(frozen=True)
class Classification:
    """One block's type, how certain it is, and everything needed to explain it later."""

    type: DescriptionType
    certainty: float
    evidence: Evidence
    tier: Tier
    model: str
    detail: str = ""

    @property
    def is_confident(self) -> bool:
        return self.type is not DescriptionType.UNKNOWN


def _unknown(tier: Tier, model: str, evidence: Evidence, detail: str) -> Classification:
    return Classification(
        type=DescriptionType.UNKNOWN,
        certainty=0.0,
        evidence=evidence,
        tier=tier,
        model=model,
        detail=detail,
    )


def _clamp_model_certainty(raw: object) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return MODEL_CERTAINTY_FLOOR
    return max(MODEL_CERTAINTY_FLOOR, min(MODEL_CERTAINTY_CEILING, value))


def classify(block: PictureBlock, *, tier: Tier, client: object | None = None) -> Classification:
    """Classify one picture block. Never raises: a failure comes back as `unknown` with a reason.

    A classification failure must not cost the book. The job continues with an `unknown` block,
    which is the same outcome as an honest abstention and is handled the same way downstream —
    but `detail` records what actually happened, so the failure is surfaced rather than swallowed.
    """
    model = model_tag_for(tier)

    signal = read_caption(block.caption)
    if signal.settled:
        assert signal.type is not None  # noqa: S101 - `settled` is the invariant
        return Classification(
            type=signal.type,
            certainty=CAPTION_CERTAINTY,
            evidence=Evidence.CAPTION,
            tier=tier,
            model=model,
            detail=f"The caption names it: {signal.term!r}. The model was not called.",
        )

    answer = _ask_model(block, tier=tier, model=model, client=client)
    if answer is None:
        return _unknown(
            tier,
            model,
            Evidence.NONE,
            f"The caption settled nothing and the {model} call did not return a usable answer.",
        )

    kind, certainty, detail = answer
    if kind is DescriptionType.UNKNOWN:
        return _unknown(tier, model, Evidence.MODEL, f"{model} answered unknown. {detail}")

    if certainty < CERTAINTY_FLOOR:
        return _unknown(
            tier,
            model,
            Evidence.MODEL,
            f"{model} answered {kind.value} at {certainty:.2f}, below the "
            f"{CERTAINTY_FLOOR:.2f} floor. The answer was discarded rather than used.",
        )

    return Classification(
        type=kind,
        certainty=certainty,
        evidence=Evidence.MODEL,
        tier=tier,
        model=model,
        detail=detail,
    )


def _ask_model(
    block: PictureBlock, *, tier: Tier, model: str, client: object | None
) -> tuple[DescriptionType, float, str] | None:
    """One vision call. Returns None when anything at all went wrong."""
    resolved = client
    if resolved is None:
        try:
            import ollama
        except Exception:
            # A damaged installation. The environment check reports this properly at startup
            # (ARCHITECTURE section 6); here it is one more block that cannot be typed.
            return None
        resolved = ollama.Client(host=resolve_host(), timeout=REQUEST_TIMEOUT_SECONDS)

    try:
        response = resolved.generate(  # type: ignore[attr-defined]
            model=model,
            prompt=build_prompt(block.caption, block.context),
            images=[block.image],
            format=RESPONSE_SCHEMA,
        )
        payload = json.loads(response.response)
        kind = DescriptionType(str(payload["type"]))
        if kind not in CLASSIFIABLE_TYPES:
            # The answer set is enforced by Ollama through the schema rather than by us, so an
            # answer outside it means the schema was not applied. Every member is currently
            # classifiable (ADR-028), which makes this unreachable today and worth keeping: it is
            # what stops a future narrowing of the set from being silently unenforced.
            return None
    except Exception:
        # Unreachable Ollama, a missing model, a timeout, or a reply that did not match the
        # schema. They differ in cause and not in what this component can do about them, and the
        # environment check (ARCHITECTURE section 6) is what tells a user which one it was.
        return None

    certainty = _clamp_model_certainty(payload.get("certainty"))
    return kind, certainty, f"{model} answered {kind.value} at {certainty:.2f}."


def classify_all(
    blocks: list[PictureBlock], *, tier: Tier, client: object | None = None
) -> list[Classification]:
    """Classify blocks in order, one call each.

    Sequential on purpose. Ollama serves one request at a time per model, so concurrency here
    would queue rather than overlap, and jobs already run one at a time (ARCHITECTURE section 11).
    This is the seam a future batching change would use, not an argument that none is possible.
    """
    return [classify(block, tier=tier, client=client) for block in blocks]
