# STATE

**Snapshot, not history.** Where the build stands right now, so a fresh session can answer "where are we" from one file. Reasoning lives in `DECISIONS.md`, the released record in `CHANGELOG.md`, the design in `ARCHITECTURE.md`. This file does not restate them.

**Every line below was checked against the repository or a command run when it was written.** Where something could not be verified, it says so rather than being left out. Regenerated whenever a component lands, an ADR is added, or a gap opens or closes (`CLAUDE.md` §6).

**Verified:** 2026-08-10

---

## Position

| | |
|---|---|
| Version | 0.1.0 (`pyproject.toml`, confirmed by `asoy --version`) |
| Branch / commit | `main` at `82393cc`. This is the commit the lines below were verified against; the commit carrying an update to this file is always one later than the commit it describes |
| Push state | `origin/main` was at `1c88dad` when this was verified, behind the local branch above. Anything reading this repository from GitHub sees that commit, not the one in the row above. **State the sync point, never a count** — a count is wrong the moment either side moves, and this line has gone stale twice that way |
| Tests | 304 passing, 2 deselected (fences 59, classifier 42, classifier-reference 39 of which 2 need Ollama, environment 36, pipeline 38, tiers 26, router 24, smoke 22, calibre 20) |
| Highest ADR | ADR-028 |
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
| Block classifier: pre-pass, abstention rule, failure paths | `uv run pytest tests/test_classifier.py` |
| Classifier harness (its metrics, not its accuracy) | `uv run pytest tests/test_classifier_reference.py` |
| Whole suite | `uv run pytest` |
| License cleanliness | `uv run pip-licenses --format=markdown` |

## Partially built

- **Orchestrator** (`ARCHITECTURE` 4.2). Converts one document start to finish and asserts chapter counts between parse and emit. Missing: checkpointing and resume (ADR-015), the job record, cancellation, and the queue. A crashed job restarts from nothing.
- **Desktop shell** (4.1). Window opens; the JS bridge returns version, tier, and environment. Missing: file picker, job queue, progress reporting, review screen. Nothing can be converted from the UI — only from `asoy convert`.
- **Parser** (4.4). Chapters, headings, verbatim text, and non-text blocks carried in reading order. Tables arrive with their cells when Docling extracts them cleanly.
- **Assembler and exporter** (4.8, 4.9). The delimiter is defined, emitted, and parsed (ADR-025). Every picture becomes a `failed` description with placeholder text, because there is no generator to produce a real one — correct interim behaviour under invariant 7, not finished behaviour.
- **Block classifier** (4.6). Caption pre-pass, tier-model call, abstention rule, and the measurement harness all exist (ADR-026, ADR-027, ADR-028). Its answer set includes `table`, because a scanned table arrives as a picture block (ADR-028). **Not wired to anything**: the parser still types every picture `unknown` and nothing calls `classify`. It landed with its harness rather than with a consumer, so wiring it into the parser is a separate change.
- **Format router** (4.3). Complete for every accepted format, but only EPUB and ODT have been converted end to end. PDF, DOCX, PPTX, XLSX, HTML, images, and plain text route correctly and have **never been run through a conversion**.

## Not started

- **OCR layer** (4.5) and **description generator** (4.7). Both are docstring-only stubs in `src/asoy/`. Until the generator exists every picture description is `failed`.
- **Update check** (9), installer, and code signing.

## Open gaps and unresolved questions

- **The Calibre path has never run against the real `ebook-convert`.** Calibre is not installed on the development machine; every test drives a generated `.cmd` stand-in that mimics its exit codes and output. The one-off check to run once it is available is in `RUNBOOK` §3 under *Outstanding manual verification*.
- **The CPU tier has never been exercised.** The development machine detects GPU. `moondream:v2` is not pulled, so the CPU-tier model tag in `environment.py` remains unverified — a wrong tag would present as a "model not pulled" message that pulling does not fix. The GPU tag `qwen3-vl:4b` is confirmed by `asoy --check` passing.
- **GPU-tier conversion speed is not what `ARCHITECTURE` §5 implies** (ADR-021). The tier delivers better descriptions but not faster conversion; the layout pass and OCR both run on CPU. Unmeasured, and no benchmark exists because no full conversion has been timed.
- **The parser depends on a private Docling attribute** to close the source file (ADR-024). A Docling upgrade breaks it silently by design; two named tests are the only guard.
- **Every picture in every book currently converts to a placeholder.** The output is honest and it is not useful yet. This is the single largest gap between what Asoy does and what it is for.
- **The classifier's accuracy is unmeasured.** `reference/classifier/` is empty — the public-domain books are being gathered — so no acceptance number in ADR-026, ADR-027, or ADR-028 has been measured against anything. The harness runs and the acceptance test skips loudly rather than passing on no evidence.
- **The classification prompt is unratified.** It is isolated in `src/asoy/classifier/prompt.py` and marked, and `CLAUDE.md` §5 treats prompts as ask-first. It has never been compared against an alternative.
- **`CERTAINTY_FLOOR` is a placeholder, not a considered value.** It moves the measured `unknown` rate almost directly and should be set from the reference set once that exists.
- **One input cannot be represented**: author text containing a line that is exactly `<!-- /asoy:text -->`. It raises and writes nothing rather than emitting a file that misparses itself (ADR-025). Requires a book to contain Asoy's own closing marker verbatim.
- **The table narration form has been read, not heard.** A table becomes `A table of 2 columns and 2 rows. The columns are: Name, Year.` then `Row 1. Name, Ada. Year, 1843.` It was chosen for the ear and has never been through a text-to-speech engine. **Needs a listening pass before 1.0**, on a real table of more than three columns, where naming every column on every row may prove tiring rather than clarifying.
- **Runs of whitespace collapse in EPUB and HTML** (`ARCHITECTURE` §11). Decided and documented, not a defect, listed here so it is not rediscovered.
- **Anything reading this repository from GitHub sees the default branch as pushed, not as it stands locally.** The position table above says where that is. Uncommitted work and unpushed commits are invisible to it.

## The next move

**Gather the reference sets.** Two components now depend on material that does not exist: the classifier's acceptance bar cannot be measured, and the description generator cannot be built responsibly without its own set, since prompt quality is measured against a reference set or it is not measured (`CLAUDE.md` §9). About 70 public-domain picture blocks from four or more distinct sources, per `reference/classifier/README.md` and the sourcing rules in ADR-028.

Triage found two usable sources, not three: Brinton (149 picture blocks, the only chart source) and *The Boy Mechanic*, whose two volumes count as one source. Still needed: two more sources, one of them with type-naming captions, and a group of about 10 scanned-table blocks from at least two sources, without which ADR-028's reversal condition is unmeasurable.

The description generator (4.7) remains the largest gap in the product, and building it before there is anything to measure it with would repeat the position the classifier is in now: complete, plausible, and unevidenced.

---

*Companion documents: `ARCHITECTURE.md` (what the system is), `DECISIONS.md` (why), `CHANGELOG.md` (what shipped), `RUNBOOK.md` (how to operate it).*
