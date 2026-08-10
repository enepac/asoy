# Asoy

Converts books into text prepared for audiobook narration, entirely on your own machine.

## The name

*Asoy* is Cebuano and Hiligaynon. In Cebuano it means to narrate, relate, or recount. In Hiligaynon it carries a further sense: to explain, to expound, to make clear. That second meaning is the product. Extracting text from a book is a solved problem; taking the chart, the diagram, and the photograph and making them clear in words is what this application exists to do.

## What it does

- Reads common ebook and document formats (EPUB, PDF, DOCX, PPTX, XLSX, HTML, images, plain text) and extracts the author's text **verbatim**, never summarised or corrected.
- Turns every non-text element (photographs, illustrations, tables, diagrams, charts) into a written narrative description placed in its correct reading position, so a listener hears an account of the visual content instead of silence.
- Marks every generated description with an explicit delimiter carrying its type and confidence, which keeps descriptions distinguishable from author text and makes voice switching possible downstream.
- Runs fully locally. No book content, page image, extracted text, or filename is transmitted anywhere. The only outbound request is an optional version check that sends the version string and nothing else.

## Status

**Pre-release.** There is no installer and no published build yet, so Asoy is not installable at this time. The documents in this repository describe the system and the decisions behind it; treat any version number, date, or release artifact reference in them as not yet issued.

## Requirements

- **Windows.** Windows is the only supported platform (ADR-007).
- **[Ollama](https://ollama.com), installed separately.** Asoy does not bundle the model that writes descriptions. It verifies at first run that Ollama is installed, reachable, and has the required model pulled.
- **An NVIDIA GPU with 6 GB of video memory or more (optional).** With one, Asoy runs the GPU tier: fuller, more accurate descriptions and substantially faster conversion. Without one, it falls back to the CPU tier. The active tier is always shown in the interface and recorded with each job.
- **[Calibre](https://calibre-ebook.com) (optional).** Required only for Kindle and legacy ebook formats (MOBI, AZW, AZW3, FB2), which Asoy converts by calling Calibre as a separate command-line program.

DRM-protected files are rejected at ingestion by design. Asoy contains no DRM circumvention.

## Documentation

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | What each component does, how data flows, and where it lives |
| [DECISIONS.md](docs/DECISIONS.md) | Why the system is built this way, with rejected alternatives and reversal conditions |
| [DATA.md](docs/DATA.md) | What is stored, where, for how long, and what is never transmitted |
| [SUPPORT.md](docs/SUPPORT.md) | Setup, troubleshooting, and the documented limitations |
| [RUNBOOK.md](docs/RUNBOOK.md) | Release, rollback, and triage procedures |
| [INCIDENTS.md](docs/INCIDENTS.md) | What has broken before, and the guards added since |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each release, including which models shipped |
| [CLAUDE.md](CLAUDE.md) | Working instructions for AI sessions: invariants, blast radius, conventions |

New readers should start with `docs/ARCHITECTURE.md`. Users looking for setup help or a known limitation should start with `docs/SUPPORT.md`.

## License

Apache License 2.0. See [LICENSE](LICENSE).

Asoy takes its licensing boundaries seriously: Calibre is invoked as a subprocess rather than linked (ADR-010), and AGPL dependencies are excluded (ADR-011). The choice of Apache 2.0 is recorded as ADR-012 in `docs/DECISIONS.md`.
