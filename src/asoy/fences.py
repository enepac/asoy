"""The output contract: HTML comment fences (ADR-025, ARCHITECTURE section 4.8).

This module is the single source of truth for the delimiter. Nothing else in Asoy writes a
marker, and nothing else reads one. It is deliberately top-level rather than tucked under the
assembler, because it is the public interface a downstream text-to-speech pipeline integrates
against and should be the first file someone looks in.

**The delimiter is a public interface (ADR-006).** Adding an attribute is a MINOR release.
Renaming one, reordering them, or changing a marker's shape is a MAJOR release. This module
carries a parser as well as an emitter so that a change breaking the format fails a round-trip
test here rather than reaching someone's pipeline.

Three markers, all valid CommonMark HTML comments and therefore invisible when rendered:

    <!-- asoy:document version="1" tier="gpu" model="qwen3-vl:4b" -->

    <!-- asoy:description type="chart" confidence="0.82" status="ok" -->
    Description prose here.
    <!-- /asoy:description -->

    <!-- asoy:text -->
    # Author's own hash, not a chapter heading.
    <!-- /asoy:text -->

**Author text is never modified, and never escaped.** A backslash inserted to tame a Markdown
metacharacter is a character a naive engine reads aloud, which makes escaping a worse defect than
the ambiguity it fixes. Where author text would be misread as structure, or as one of Asoy's own
markers, the block is wrapped in a text fence instead. The fence is used only where it is needed,
so ordinary prose stays unadorned.

Only two kinds of character in an emitted file are Asoy's: the markers here, and the `#` of a
heading. Everything else came from the author or is inside a description fence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

VERSION = "1"

# Every marker starts with this. The collision argument in ADR-025 rests on it: author text will
# essentially never contain the string, so a book cannot forge a delimiter by accident.
NAMESPACE = "asoy"

DOCUMENT = f"{NAMESPACE}:document"
DESCRIPTION = f"{NAMESPACE}:description"
TEXT = f"{NAMESPACE}:text"

MAX_HEADING_LEVEL = 6
CHAPTER_HEADING_LEVEL = 1


class DescriptionType(StrEnum):
    """What the described block is. Closed set for v1; adding a member is a MINOR release."""

    PHOTOGRAPH = "photograph"
    ILLUSTRATION = "illustration"
    TABLE = "table"
    DIAGRAM = "diagram"
    CHART = "chart"
    UNKNOWN = "unknown"


class DescriptionStatus(StrEnum):
    """Whether a description was produced. A failed one still carries readable placeholder text."""

    OK = "ok"
    FAILED = "failed"


class FenceError(ValueError):
    """The document could not be emitted or parsed as a well-formed fenced document."""


class UnfenceableText(FenceError):
    """Author text contains a closing text marker, so no fence can safely contain it.

    Vanishingly rare and deliberately loud. Emitting the block anyway would produce a file whose
    own parser reads part of the author's prose as Asoy's structure, which is the one failure this
    format exists to make impossible. See ADR-025.
    """


@dataclass(frozen=True)
class DocumentHeader:
    """The first line of every Markdown artifact: what produced this file."""

    tier: str
    model: str
    version: str = VERSION


@dataclass(frozen=True)
class HeadingSegment:
    """A heading. The `#` characters are Asoy's; the text is the author's."""

    level: int
    text: str


@dataclass(frozen=True)
class AuthorSegment:
    """One block of the author's own text, reproduced byte for byte."""

    text: str


@dataclass(frozen=True)
class DescriptionSegment:
    """One generated description of a non-text block."""

    type: DescriptionType
    confidence: float
    status: DescriptionStatus
    body: str


Segment = HeadingSegment | AuthorSegment | DescriptionSegment


@dataclass(frozen=True)
class FencedDocument:
    """A Markdown artifact: its header and its segments in reading order."""

    header: DocumentHeader
    segments: tuple[Segment, ...]

    @property
    def chapter_count(self) -> int:
        """Top-level headings. The parse-to-emit assertion counts these."""
        return sum(
            1
            for segment in self.segments
            if isinstance(segment, HeadingSegment) and segment.level == CHAPTER_HEADING_LEVEL
        )


# --- Emitting -----------------------------------------------------------------------------------


def format_confidence(value: float) -> str:
    """Two decimals, 0.00 to 1.00.

    The number is an uncalibrated heuristic derived from the model's response and the block's
    classification certainty. It orders descriptions by how much they are worth reviewing. It is
    not a probability and must not be read as one.
    """
    if not 0.0 <= value <= 1.0:
        raise FenceError(f"Confidence must be between 0.00 and 1.00, got {value}.")
    return f"{value:.2f}"


def document_header(header: DocumentHeader) -> str:
    """The document header line."""
    return (
        f'<!-- {DOCUMENT} version="{header.version}" '
        f'tier="{header.tier}" model="{header.model}" -->'
    )


def description_fence(segment: DescriptionSegment) -> str:
    """One description, opened and closed. All three attributes, always, in this order."""
    if not segment.body.strip():
        raise FenceError(
            "A description fence must carry readable text. Invariant 7: a gap where a "
            "description should be is indistinguishable from the content not existing."
        )

    open_marker = (
        f'<!-- {DESCRIPTION} type="{segment.type.value}" '
        f'confidence="{format_confidence(segment.confidence)}" '
        f'status="{segment.status.value}" -->'
    )
    return f"{open_marker}\n{segment.body.strip()}\n<!-- /{DESCRIPTION} -->"


def text_fence(text: str) -> str:
    """Wrap author text so nothing in it is read as structure or as one of Asoy's markers."""
    if _CLOSING_TEXT_LINE.search(text):
        raise UnfenceableText(
            "Author text contains a line that is exactly the closing text marker, so no fence "
            "can hold it without the file's own parser closing early. Nothing was written."
        )
    return f"<!-- {TEXT} -->\n{text}\n<!-- /{TEXT} -->"


def heading_line(segment: HeadingSegment) -> str:
    """A heading line. The only place Asoy adds a Markdown metacharacter to author text."""
    level = max(1, min(segment.level, MAX_HEADING_LEVEL))
    return f"{'#' * level} {segment.text}"


def emit_author_text(text: str) -> str:
    """Author text as it will appear, fenced only if it needs to be."""
    return text_fence(text) if needs_fence(text) else text


def render(document: FencedDocument) -> str:
    """Render to Markdown. The inverse of `parse`."""
    parts = [document_header(document.header)]
    for segment in document.segments:
        if isinstance(segment, DescriptionSegment):
            parts.append(description_fence(segment))
        elif isinstance(segment, HeadingSegment):
            parts.append(heading_line(segment))
        else:
            parts.append(emit_author_text(segment.text))
    return "\n\n".join(parts) + "\n"


def flatten(document: FencedDocument) -> str:
    """Render to plain text: no markers, no heading characters, descriptions as ordinary prose.

    This is the `.txt` artifact (ARCHITECTURE section 4.9). It carries nothing of Asoy's own
    syntax, because its whole purpose is to be read by a pipeline that cannot parse the fences.
    """
    parts: list[str] = []
    for segment in document.segments:
        if isinstance(segment, DescriptionSegment):
            parts.append(segment.body.strip())
        elif isinstance(segment, HeadingSegment):
            parts.append(segment.text)
        else:
            parts.append(segment.text)
    return "\n\n".join(parts) + "\n" if parts else ""


# --- Deciding when author text needs a fence ----------------------------------------------------

# Lines a Markdown parser would read as structure rather than as prose. A heading, a list marker,
# or a blockquote arrow can interrupt a paragraph, so every line is checked and not only the
# first. Over-fencing costs a reader nothing; under-fencing changes what the author wrote.
_STRUCTURAL_LINE = re.compile(
    r"""^(?:
        \#{1,6}(?:\s|$)             # ATX heading
      | >                           # blockquote
      | [-*+](?:\s|$)               # bullet list
      | \d{1,9}[.)](?:\s|$)         # ordered list
      | (?:\ {4,}|\t)               # indented code
      | (?:```|~~~)                 # fenced code
      | \|                          # table row
      | (?:-{3,}|_{3,}|\*{3,})\s*$  # thematic break
      | =+\s*$                      # setext underline
      | <                           # HTML block, which includes a comment
    )""",
    re.VERBOSE,
)

# Any line opening an HTML comment on the Asoy namespace. Broader than the three real markers on
# purpose: a near miss is fenced too, so text emitted today cannot forge a marker added later.
_MARKER_LINE = re.compile(rf"<!--\s*/?\s*{re.escape(NAMESPACE)}:")

_CLOSING_TEXT_LINE = re.compile(rf"^[ \t]*<!--\s*/{re.escape(TEXT)}\s*-->[ \t]*$", re.MULTILINE)


def needs_fence(text: str) -> bool:
    """True when this author block must be wrapped to survive a Markdown parser intact."""
    if _MARKER_LINE.search(text):
        return True
    return any(_STRUCTURAL_LINE.match(line) for line in text.splitlines())


# --- Parsing ------------------------------------------------------------------------------------

_HEADER_LINE = re.compile(
    rf'^<!--\s*{re.escape(DOCUMENT)}\s+version="([^"]*)"\s+tier="([^"]*)"\s+model="([^"]*)"\s*-->$'
)

_DESCRIPTION_OPEN = re.compile(
    rf'^<!--\s*{re.escape(DESCRIPTION)}\s+type="([^"]*)"\s+'
    r'confidence="([^"]*)"\s+status="([^"]*)"\s*-->$'
)

_DESCRIPTION_CLOSE = re.compile(rf"^<!--\s*/{re.escape(DESCRIPTION)}\s*-->$")
_TEXT_OPEN = re.compile(rf"^<!--\s*{re.escape(TEXT)}\s*-->$")
_TEXT_CLOSE = re.compile(rf"^<!--\s*/{re.escape(TEXT)}\s*-->$")
_HEADING = re.compile(r"^(#{1,6}) (.*)$")


def _flush(buffer: list[str], segments: list[Segment]) -> None:
    """Turn accumulated unfenced lines into author segments, split on blank lines."""
    block: list[str] = []
    for line in buffer:
        if line.strip():
            block.append(line)
            continue
        if block:
            segments.append(AuthorSegment(text="\n".join(block)))
            block = []
    if block:
        segments.append(AuthorSegment(text="\n".join(block)))
    buffer.clear()


def parse(markdown: str) -> FencedDocument:
    """Parse a Markdown artifact back into its header and segments. The inverse of `render`.

    Raises FenceError on anything malformed rather than guessing. A parser that repairs its input
    hides the emitter defect it exists to catch.
    """
    lines = markdown.split("\n")

    header_match = _HEADER_LINE.match(lines[0]) if lines else None
    if header_match is None:
        raise FenceError(
            f"The first line must be the {DOCUMENT} header, got "
            f"{(lines[0] if lines else '')!r}."
        )
    version, tier, model = header_match.groups()

    segments: list[Segment] = []
    buffer: list[str] = []
    index = 1

    while index < len(lines):
        line = lines[index]

        if _TEXT_OPEN.match(line):
            _flush(buffer, segments)
            index, body = _read_until(lines, index + 1, _TEXT_CLOSE, TEXT)
            segments.append(AuthorSegment(text="\n".join(body)))
            continue

        description_open = _DESCRIPTION_OPEN.match(line)
        if description_open is not None:
            _flush(buffer, segments)
            index, body = _read_until(lines, index + 1, _DESCRIPTION_CLOSE, DESCRIPTION)
            segments.append(_description(*description_open.groups(), "\n".join(body)))
            continue

        if _DESCRIPTION_CLOSE.match(line) or _TEXT_CLOSE.match(line):
            raise FenceError(f"Closing marker with nothing open, at line {index + 1}.")

        heading = _HEADING.match(line)
        if heading is not None:
            _flush(buffer, segments)
            segments.append(HeadingSegment(level=len(heading.group(1)), text=heading.group(2)))
            index += 1
            continue

        buffer.append(line)
        index += 1

    _flush(buffer, segments)
    return FencedDocument(
        header=DocumentHeader(tier=tier, model=model, version=version),
        segments=tuple(segments),
    )


def _read_until(
    lines: list[str], start: int, closing: re.Pattern[str], name: str
) -> tuple[int, list[str]]:
    """Collect lines up to the closing marker. Returns the index after it, and the body."""
    body: list[str] = []
    index = start
    while index < len(lines):
        if closing.match(lines[index]):
            return index + 1, body
        body.append(lines[index])
        index += 1
    raise FenceError(f"A {name} fence was opened at line {start} and never closed.")


def _description(kind: str, confidence: str, status: str, body: str) -> DescriptionSegment:
    """Build a description segment, rejecting anything outside the closed sets."""
    try:
        parsed_type = DescriptionType(kind)
    except ValueError:
        raise FenceError(
            f"{kind!r} is not one of the v1 description types: "
            f"{', '.join(t.value for t in DescriptionType)}."
        ) from None

    try:
        parsed_status = DescriptionStatus(status)
    except ValueError:
        raise FenceError(f"{status!r} is not a description status.") from None

    if not re.fullmatch(r"[01]\.\d{2}", confidence):
        raise FenceError(f"Confidence must be two decimals from 0.00 to 1.00, got {confidence!r}.")

    return DescriptionSegment(
        type=parsed_type,
        confidence=float(confidence),
        status=parsed_status,
        body=body.strip("\n"),
    )


def strip_fences(markdown: str) -> str:
    """The flattened form of a Markdown artifact, derived from the artifact itself.

    The exporter builds the `.txt` from the same document object rather than calling this, so this
    exists for a consumer holding only the `.md` — and as the check that the two agree.
    """
    return flatten(parse(markdown))
