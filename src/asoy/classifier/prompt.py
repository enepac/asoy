"""The classification prompt and its response schema (ARCHITECTURE section 4.6, ADR-026).

**UNRATIFIED. This prompt has not been approved and has not been measured.**

CLAUDE.md section 5 names the description generator's prompts as ask-first. It does not obviously
cover this one, which selects a type rather than producing prose a user hears — but it is a prompt
whose wording moves the product's quality, so it is treated as ask-first and is isolated in this
module so that approving or replacing it is a one-file change.

Two things must both happen before this stops being provisional:

1. It is approved, or replaced, on the planning surface.
2. It is measured against the committed reference set (`reference/classifier/`), which does not
   exist yet. Until it does, every acceptance number for this component is unmeasured. "It looks
   reasonable" is not evidence — CLAUDE.md section 9 names that failure by name.

Do not tune the wording here against a handful of examples and call it improved. The reference
set is the instrument; without it a change to this file is a change of unknown sign.
"""

from __future__ import annotations

from asoy.fences import DescriptionType

# What the model may answer. Every member of DescriptionType except `table`, which is excluded
# deliberately rather than forgotten: the parser types tables from their own extracted structure
# and they never reach the classifier (ARCHITECTURE 4.6). Offering the label would invite the
# model to apply it to a picture of a table, which would then be sent down the structural path
# that has no cells to render.
CLASSIFIABLE_TYPES: tuple[DescriptionType, ...] = (
    DescriptionType.PHOTOGRAPH,
    DescriptionType.ILLUSTRATION,
    DescriptionType.DIAGRAM,
    DescriptionType.CHART,
    DescriptionType.UNKNOWN,
)

# The model answers into this schema rather than into free text. Ollama constrains generation to
# it, so the reply cannot arrive as prose that needs guessing at, and an unparseable response
# becomes an impossible case rather than an error path that fires in the field.
RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": [kind.value for kind in CLASSIFIABLE_TYPES]},
        "certainty": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["type", "certainty"],
}

# UNRATIFIED, see the module docstring. The distinctions it draws are the ones the reference set
# is built to measure: pictorial against graphical first, then within each pair.
CLASSIFICATION_PROMPT = """You are labelling one visual element taken from a book, so that it can \
later be described aloud for an audiobook listener.

Answer with the single label that best fits what the element IS, not what it depicts:

- photograph: a camera image of something real.
- illustration: a drawing, painting, engraving, portrait, or any other hand-made picture.
- diagram: a figure explaining structure, process, or place. Schematics, maps, cutaways, \
flowcharts.
- chart: a figure presenting data. Axes, plotted series, bars, pie segments, scales.
- unknown: you cannot tell, or it is none of these.

Choose unknown rather than guessing. A wrong label is worse than no label, because it selects the \
wrong approach for describing the element later.

Also give your certainty from 0 to 1."""

# The caption and nearby prose, when there are any, are appended to the prompt. The pre-pass has
# already failed to settle the block from this text, so what is left is the non-decisive part —
# useful to a model that can weigh it against the image, useless as a rule.
CONTEXT_TEMPLATE = """

Text near this element in the book, which may or may not describe it:
{context}"""


def build_prompt(caption: str = "", context: str = "") -> str:
    """The full prompt for one block, including whatever surrounding text is available."""
    nearby = "\n".join(part.strip() for part in (caption, context) if part.strip())
    if not nearby:
        return CLASSIFICATION_PROMPT
    return CLASSIFICATION_PROMPT + CONTEXT_TEMPLATE.format(context=nearby)
