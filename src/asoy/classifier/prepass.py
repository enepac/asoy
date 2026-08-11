"""The caption and context pre-pass (ARCHITECTURE section 4.6, ADR-026).

Most books say what their pictures are. A caption reading "Figure 12. Photograph of the north
face" has already answered the question, and asking a vision model costs seconds of GPU time to
recover an answer that was sitting in the text. This module reads that text.

**It settles or it abstains. It never guesses.** A caption that matches terms from two families,
or none, returns no answer and the block goes to the model. A weak guess here would be worse than
no answer, because it would be spent instead of the model call rather than alongside it.

The pre-pass's conclusion is never shown to the model. If the caption were decisive the model is
not called at all, so there is nothing to pass on; and keeping the two independent means a future
change that does run both can treat their agreement as evidence rather than as an echo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from asoy.fences import DescriptionType

# Terms that name a picture's kind outright. Only unambiguous ones belong here: each has to be a
# word an author uses to say what the thing *is*, not what it depicts. "Portrait" earns its place
# because a portrait is an artwork; "landscape" does not, because it describes a subject that a
# photograph and a painting share.
#
# Deliberately absent: "figure", "plate", "image", "picture", "exhibit". Every one of them appears
# in front of all four families and would settle nothing.
TERMS: dict[DescriptionType, frozenset[str]] = {
    DescriptionType.PHOTOGRAPH: frozenset(
        {"photograph", "photographs", "photo", "photos", "photographed", "snapshot"}
    ),
    DescriptionType.ILLUSTRATION: frozenset(
        {
            "illustration",
            "illustrations",
            "drawing",
            "drawings",
            "engraving",
            "engravings",
            "etching",
            "woodcut",
            "lithograph",
            "painting",
            "portrait",
            "sketch",
            "cartoon",
            "frontispiece",
        }
    ),
    DescriptionType.DIAGRAM: frozenset(
        {
            "diagram",
            "diagrams",
            "schematic",
            "schematics",
            "map",
            "maps",
            "flowchart",
            "floorplan",
            "blueprint",
            "cross-section",
            "cutaway",
        }
    ),
    DescriptionType.CHART: frozenset(
        {
            "chart",
            "charts",
            "graph",
            "graphs",
            "histogram",
            "scatterplot",
            "plot",
            "plotted",
            "barchart",
        }
    ),
}

# Only the caption is decisive. Surrounding prose mentioning a chart three sentences away is not
# a statement about this block, so context is collected for the model call and is not read here.
_WORD = re.compile(r"[a-z][a-z-]*")


@dataclass(frozen=True)
class TextSignal:
    """What the caption said, if anything.

    `type` is None when the caption named no family or named more than one. `term` records the
    word that decided it, so a misclassification traced back here names the cause rather than
    requiring the caption to be re-read by hand.
    """

    type: DescriptionType | None
    term: str = ""

    @property
    def settled(self) -> bool:
        return self.type is not None


NO_SIGNAL = TextSignal(type=None)


def read_caption(caption: str) -> TextSignal:
    """Read a caption for a term naming the picture's family. Abstains unless exactly one matches.

    Abstention is the common case and is not a failure — it is the pre-pass declining to spend
    the model's answer on a guess.
    """
    words = set(_WORD.findall(caption.lower()))
    if not words:
        return NO_SIGNAL

    matches = {
        kind: sorted(words & terms) for kind, terms in TERMS.items() if words & terms
    }
    if len(matches) != 1:
        # Zero families named, or two — "a diagram after a photograph by Nadar" is genuinely
        # ambiguous about which is the block, so it goes to the model rather than to a coin toss.
        return NO_SIGNAL

    kind, found = next(iter(matches.items()))
    return TextSignal(type=kind, term=found[0])
