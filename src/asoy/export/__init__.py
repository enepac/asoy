"""Exporter: writes the canonical Markdown and the flattened text (ARCHITECTURE section 4.9).

Two artifacts per job: the `.md`, which is the source of truth, and a `.txt` derived from it.

**Silent truncation looks like success**, which is why the written files are read back and
re-counted here rather than trusted. A short write, a full disk, or an encoding failure would
otherwise leave a plausible-looking half a book on disk with a zero exit code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from asoy.assemble import RenderedDocument, count_chapter_headings

MARKDOWN_SUFFIX = ".md"
TEXT_SUFFIX = ".txt"
ENCODING = "utf-8"


class OutputVerificationError(RuntimeError):
    """A written artifact did not match what was rendered."""


@dataclass(frozen=True)
class WrittenArtifacts:
    markdown_path: Path
    text_path: Path
    chapter_count: int
    description_count: int = 0
    failed_description_count: int = 0


def _write_and_verify(path: Path, content: str) -> None:
    path.write_text(content, encoding=ENCODING, newline="\n")
    written = path.read_text(encoding=ENCODING)
    if written != content:
        raise OutputVerificationError(
            f"{path} does not match what was rendered: "
            f"expected {len(content)} characters, read back {len(written)}."
        )


def write(rendered: RenderedDocument, output_dir: Path, stem: str) -> WrittenArtifacts:
    """Write both artifacts, verifying each against what was rendered."""
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = output_dir / f"{stem}{MARKDOWN_SUFFIX}"
    text_path = output_dir / f"{stem}{TEXT_SUFFIX}"

    _write_and_verify(markdown_path, rendered.markdown)
    _write_and_verify(text_path, rendered.plain_text)

    # Counted by parsing the file back, not by scanning it. Since ADR-025 a `#` at the start of a
    # line may be the author's, wrapped in a text fence, and counting it would fail a correct job.
    on_disk = count_chapter_headings(markdown_path.read_text(encoding=ENCODING))
    if on_disk != rendered.titled_chapter_count:
        raise OutputVerificationError(
            f"{markdown_path} contains {on_disk} chapter headings, "
            f"but {rendered.titled_chapter_count} were rendered."
        )

    return WrittenArtifacts(
        markdown_path=markdown_path,
        text_path=text_path,
        chapter_count=rendered.chapter_count,
        description_count=rendered.description_count,
        failed_description_count=rendered.failed_description_count,
    )
