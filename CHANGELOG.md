# CHANGELOG

All notable changes to **Asoy** are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com). Versioning follows [Semantic Versioning](https://semver.org), with the project-specific definitions below.

---

## Conventions

**This file is for users.** Write what changed from the outside, in terms someone converting a book would recognise. Internal refactors, dependency bumps that change nothing observable, and documentation edits do not belong here — they belong in the commit history.

**Write the entry before building the release**, not after. An entry written afterward is written from memory, and the release and the record are then free to disagree.

**Never rewrite a published entry.** If it was wrong, add a correction to the next release rather than editing history. Someone has already read it.

### Categories

Use these headings, in this order, omitting any that are empty:

- **Added** — new capability
- **Changed** — existing behaviour now works differently
- **Output** — anything that changes what the converted file looks like *(project-specific; see below)*
- **Deprecated** — still works, will be removed
- **Removed** — gone
- **Fixed** — a defect corrected
- **Security** — a vulnerability addressed
- **Privacy** — anything touching what is stored or transmitted *(project-specific; see below)*

### What counts as a major version

A MAJOR bump is required for:

- Any change to the description delimiter's shape or attribute names. Users parse this in their own pipelines (`docs/DECISIONS.md` ADR-006).
- Removing support for an input format.
- Changing the structure of the output files in a way that breaks a consumer reading the previous version.

MINOR covers new formats, new capabilities, and model changes (below). PATCH covers fixes that leave behaviour otherwise unchanged.

### Model changes get their own attention

**A model change alters the output for identical input without changing any interface.** A user who reconverts a book and gets different descriptions will experience that as a breaking change even though nothing in the format moved.

So: any change to the model used by either tier is at minimum a MINOR release, appears under **Output**, and names the old and new model explicitly. Every release records which models it shipped with, so anyone can explain why last month's conversion reads differently from today's.

### The Privacy category is not optional

Any change to what Asoy stores or transmits appears under **Privacy**, prominently, never folded into another category. This is the project's central promise (`docs/DATA.md` §9). If a release has nothing to say here, the heading is simply absent — which is itself the normal state.

---

## [Unreleased]

*Nothing yet.*

---

## [1.0.0] — [DATE]

First public release.

### Added

- Conversion of EPUB, PDF, DOCX, PPTX, XLSX, HTML, images, and plain text into text prepared for audiobook narration.
- Conversion of MOBI, AZW, AZW3, FB2, and other legacy ebook formats, via Calibre where it is installed.
- Narrative descriptions of non-text content — photographs, illustrations, tables, diagrams, and charts — placed in correct reading order rather than skipped.
- Optical character recognition for scanned books and image-only PDFs.
- Two hardware tiers, detected automatically: a GPU tier for cards with 6 GB of video memory or more, and a CPU fallback. The active tier is shown in the interface and recorded with each job.
- Review screen collecting low-confidence descriptions and flagged pages for correction before narration.
- Chapter-level checkpointing. An interrupted conversion resumes from the last completed chapter rather than restarting.
- First-run environment check verifying that Ollama is installed, running, and has the required model.

### Output

- Markdown is the canonical output format, preserving chapter structure as headings, with every generated description wrapped in an explicit delimiter carrying its type and confidence.
- A flattened plain-text export is produced alongside it, with descriptions inline as ordinary prose.
- Shipped models: **GPU tier** Qwen3-VL-4B (Q4). **CPU tier** Moondream 2.

### Privacy

- All processing is local. No book content, page image, extracted text, or filename is transmitted anywhere.
- The only outbound network request is a version check, which sends the version string and nothing else. It can be disabled in settings.
- No account, no telemetry, no analytics, no crash reporting, no installation identifier.

### Known limitations at release

Documented in full in `docs/SUPPORT.md`:

- DRM-protected files cannot be converted, by design.
- Handwriting is not reliably recognised.
- PDFs produce worse results than EPUBs, and complex layouts can produce reading-order errors.
- Chart descriptions are approximate, more so on the CPU tier, where values are frequently described qualitatively rather than numerically.
- Windows only.

---

## Model history

Which models shipped with which release. Kept so that a change in output quality can always be traced to a cause.

| Version | GPU tier | CPU tier |
|---|---|---|
| 1.0.0 | Qwen3-VL-4B (Q4) | Moondream 2 |

---

## Entry template

```
## [X.Y.Z] — YYYY-MM-DD

### Added
- 

### Changed
- 

### Output
- 

### Fixed
- 

### Security
- 

### Privacy
- 
```

---

*Companion documents: `docs/DECISIONS.md` (why changes were made), `docs/INCIDENTS.md` (what prompted the fixes), `docs/RUNBOOK.md` §3 (where in the release procedure this file is updated).*
