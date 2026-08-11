# STATE

**Snapshot, not history.** Where the build stands right now, so a fresh session can answer "where are we" from one file. Reasoning lives in `DECISIONS.md`, the released record in `CHANGELOG.md`, the design in `ARCHITECTURE.md`. This file does not restate them.

**Every line below was checked against the repository or a command run when it was written.** Where something could not be verified, it says so rather than being left out. Regenerated whenever a component lands, an ADR is added, or a gap opens or closes (`CLAUDE.md` §6).

**Verified:** 2026-08-10

---

## Position

| | |
|---|---|
| Version | 0.1.0 (`pyproject.toml`, confirmed by `asoy --version`) |
| Branch / commit | `main` at `af7ec58`. This is the commit the lines below were verified against; the commit carrying an update to this file is always one later than the commit it describes |
| Push state | In sync with `origin/main` at `af7ec58`, and one ahead of it until the commit carrying this line is itself pushed. **State the sync point, never a count** — a count is wrong the moment either side moves, and this line has gone stale twice that way |
| Tests | 218 passing (fences 54, environment 36, pipeline 36, tiers 26, router 24, smoke 22, calibre 20) |
| Highest ADR | ADR-025 |
| Dependency tree | 117 packages resolved; license scan shows no GPL-family or AGPL entry |
| Release | None. No installer, no signing, no users |

## What works

Each line names the command that proves it. All were run.

| Capability | Proof |
|---|---|
| Hardware tier detection via NVML | `uv run asoy --tier` → GPU, RTX 3050, 6.00 GiB |
| Ollama environment check | `uv run asoy --check` → ready, exit 0 |
| EPUB → `.md` + `.txt`, pictures and tables included | `uv run asoy convert book.epub -o out` |
| ODT → same, no Calibre involved | `uv run asoy convert book.odt -o out` |
| The delimiter: emit, parse, and the round trip | `uv run pytest tests/test_fences.py` |
| Tables rendered from their cells, pictures marked as placeholders | `uv run pytest tests/test_pipeline.py` |
| DRM and encryption refused at ingestion | `uv run pytest tests/test_router.py` |
| Calibre subprocess, against a stand-in only | `uv run pytest tests/test_calibre.py` |
| Whole suite | `uv run pytest` |
| License cleanliness | `uv run pip-licenses --format=markdown` |

## Partially built

- **Orchestrator** (`ARCHITECTURE` 4.2). Converts one document start to finish and asserts chapter counts between parse and emit. Missing: checkpointing and resume (ADR-015), the job record, cancellation, and the queue. A crashed job restarts from nothing.
- **Desktop shell** (4.1). Window opens; the JS bridge returns version, tier, and environment. Missing: file picker, job queue, progress reporting, review screen. Nothing can be converted from the UI — only from `asoy convert`.
- **Parser** (4.4). Chapters, headings, verbatim text, and non-text blocks carried in reading order. Tables arrive with their cells when Docling extracts them cleanly.
- **Assembler and exporter** (4.8, 4.9). The delimiter is defined, emitted, and parsed (ADR-025). Every picture becomes a `failed` description with placeholder text, because there is no generator to produce a real one — correct interim behaviour under invariant 7, not finished behaviour.
- **Format router** (4.3). Complete for every accepted format, but only EPUB and ODT have been converted end to end. PDF, DOCX, PPTX, XLSX, HTML, images, and plain text route correctly and have **never been run through a conversion**.

## Not started

- **OCR layer** (4.5), **block classifier** (4.6), **description generator** (4.7). All three are docstring-only stubs in `src/asoy/`. Until the classifier exists every picture is typed `unknown`; until the generator exists every picture description is `failed`.
- **Update check** (9), installer, and code signing.

## Open gaps and unresolved questions

- **The Calibre path has never run against the real `ebook-convert`.** Calibre is not installed on the development machine; every test drives a generated `.cmd` stand-in that mimics its exit codes and output. The one-off check to run once it is available is in `RUNBOOK` §3 under *Outstanding manual verification*.
- **The CPU tier has never been exercised.** The development machine detects GPU. `moondream:v2` is not pulled, so the CPU-tier model tag in `environment.py` remains unverified — a wrong tag would present as a "model not pulled" message that pulling does not fix. The GPU tag `qwen3-vl:4b` is confirmed by `asoy --check` passing.
- **GPU-tier conversion speed is not what `ARCHITECTURE` §5 implies** (ADR-021). The tier delivers better descriptions but not faster conversion; the layout pass and OCR both run on CPU. Unmeasured, and no benchmark exists because no full conversion has been timed.
- **The parser depends on a private Docling attribute** to close the source file (ADR-024). A Docling upgrade breaks it silently by design; two named tests are the only guard.
- **Every picture in every book currently converts to a placeholder.** The output is honest and it is not useful yet. This is the single largest gap between what Asoy does and what it is for.
- **One input cannot be represented**: author text containing a line that is exactly `<!-- /asoy:text -->`. It raises and writes nothing rather than emitting a file that misparses itself (ADR-025). Requires a book to contain Asoy's own closing marker verbatim.
- **The table renderer has been read, not listened to.** Its prose form was chosen for the ear and has never been through a text-to-speech engine.
- **Runs of whitespace collapse in EPUB and HTML** (`ARCHITECTURE` §11). Decided and documented, not a defect, listed here so it is not rediscovered.
- **Anything reading this repository from GitHub sees the default branch as pushed, not as it stands locally.** The position table above says where that is. Uncommitted work and unpushed commits are invisible to it.

## The next move

**Build the description generator** (`ARCHITECTURE` 4.7). It is what the product is named for, and it is now the only thing standing between the pipeline and a usable book: everything around it exists, the fence it emits into is defined, and each picture currently arrives as a placeholder saying a description should have been here. It needs the block classifier (4.6) alongside it, since the type selects the prompt and a picture is typed `unknown` today. Note that prompts are `CLAUDE.md` §5 ask-first and are measured against a fixed reference set, which does not exist yet — building that set is part of the work, not a follow-up.

---

*Companion documents: `ARCHITECTURE.md` (what the system is), `DECISIONS.md` (why), `CHANGELOG.md` (what shipped), `RUNBOOK.md` (how to operate it).*
