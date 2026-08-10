# STATE

**Snapshot, not history.** Where the build stands right now, so a fresh session can answer "where are we" from one file. Reasoning lives in `DECISIONS.md`, the released record in `CHANGELOG.md`, the design in `ARCHITECTURE.md`. This file does not restate them.

**Every line below was checked against the repository or a command run when it was written.** Where something could not be verified, it says so rather than being left out. Regenerated whenever a component lands, an ADR is added, or a gap opens or closes (`CLAUDE.md` §6).

**Verified:** 2026-08-10

---

## Position

| | |
|---|---|
| Version | 0.1.0 (`pyproject.toml`, confirmed by `asoy --version`) |
| Branch / commit | `main` at `a45e2b8` |
| Push state | **4 commits ahead of `origin/main`.** Last pushed: `7a9d599` |
| Tests | 149 passing (calibre 20, environment 36, pipeline 22, router 24, smoke 21, tiers 26) |
| Highest ADR | ADR-024 |
| Dependency tree | 117 packages resolved; license scan shows no GPL-family or AGPL entry |
| Release | None. No installer, no signing, no users |

## What works

Each line names the command that proves it. All were run.

| Capability | Proof |
|---|---|
| Hardware tier detection via NVML | `uv run asoy --tier` → GPU, RTX 3050, 6.00 GiB |
| Ollama environment check | `uv run asoy --check` → ready, exit 0 |
| Text-only EPUB → `.md` + `.txt` | `uv run asoy convert book.epub -o out` |
| Text-only ODT → same, no Calibre involved | `uv run asoy convert book.odt -o out` |
| DRM and encryption refused at ingestion | `uv run pytest tests/test_router.py` |
| Calibre subprocess, against a stand-in only | `uv run pytest tests/test_calibre.py` |
| Whole suite | `uv run pytest` |
| License cleanliness | `uv run pip-licenses --format=markdown` |

## Partially built

- **Orchestrator** (`ARCHITECTURE` 4.2). Converts one document start to finish and asserts chapter counts between parse and emit. Missing: checkpointing and resume (ADR-015), the job record, cancellation, and the queue. A crashed job restarts from nothing.
- **Desktop shell** (4.1). Window opens; the JS bridge returns version, tier, and environment. Missing: file picker, job queue, progress reporting, review screen. Nothing can be converted from the UI — only from `asoy convert`.
- **Parser** (4.4). Chapters, headings, and verbatim text. Non-text blocks are counted and the job is refused rather than emitting without them. Missing: everything about describing them.
- **Format router** (4.3). Complete for every accepted format, but only EPUB and ODT have been converted end to end. PDF, DOCX, PPTX, XLSX, HTML, images, and plain text route correctly and have **never been run through a conversion**.

## Not started

- **OCR layer** (4.5), **block classifier** (4.6), **description generator** (4.7). All three are docstring-only stubs in `src/asoy/`.
- **The description delimiter** (ADR-006). Undefined. This is the output contract every component above is waiting on.
- **Update check** (9), installer, and code signing.

## Open gaps and unresolved questions

- **The Calibre path has never run against the real `ebook-convert`.** Calibre is not installed on the development machine; every test drives a generated `.cmd` stand-in that mimics its exit codes and output. The one-off check to run once it is available is in `RUNBOOK` §3 under *Outstanding manual verification*.
- **The CPU tier has never been exercised.** The development machine detects GPU. `moondream:v2` is not pulled, so the CPU-tier model tag in `environment.py` remains unverified — a wrong tag would present as a "model not pulled" message that pulling does not fix. The GPU tag `qwen3-vl:4b` is confirmed by `asoy --check` passing.
- **GPU-tier conversion speed is not what `ARCHITECTURE` §5 implies** (ADR-021). The tier delivers better descriptions but not faster conversion; the layout pass and OCR both run on CPU. Unmeasured, and no benchmark exists because no full conversion has been timed.
- **The parser depends on a private Docling attribute** to close the source file (ADR-024). A Docling upgrade breaks it silently by design; two named tests are the only guard.
- **Author text is emitted with no Markdown escaping at all** (ADR-022). A paragraph legitimately beginning with `#` or `>` will be read as structure. Unsettled, and tied to the delimiter work.
- **Runs of whitespace collapse in EPUB and HTML** (`ARCHITECTURE` §11). Decided and documented, not a defect, listed here so it is not rediscovered.
- **`src/asoy/ocr/__init__.py` names Tesseract and PaddleOCR**, which ADR-019 removed in favour of RapidOCR. A stale docstring on an unimplemented stub, harmless today and wrong.
- **Four commits are unpushed.** Anything reading the repository from GitHub — including the planning surface — is four commits behind this file.

## The next move

**Define the description delimiter and record it as an ADR.** It is on the `CLAUDE.md` §5 ask-first list and is a public interface under ADR-006, so it needs a decision rather than an implementation. Nothing downstream can start without it: the classifier, the description generator, and the assembler's non-text path are all blocked on the shape of the thing they emit, and the orchestrator currently refuses any document containing a picture or a table for exactly that reason.

---

*Companion documents: `ARCHITECTURE.md` (what the system is), `DECISIONS.md` (why), `CHANGELOG.md` (what shipped), `RUNBOOK.md` (how to operate it).*
