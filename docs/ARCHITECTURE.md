# ARCHITECTURE

**Project:** Asoy
**Document status:** Specification. Describes the system as it is intended to exist when shipped. No implementation exists yet.
**Applies to:** No released version yet. This describes the target for 1.0.0.
**Last verified against code:** Not applicable. No code exists to verify against.

> This document describes what Asoy *is*, not what it was planned to be. If the code and this document disagree, the code is right and this document is a bug. Update it in the same commit as the change.

---

## 0. The name

*Asoy* is Cebuano and Hiligaynon. In Cebuano it means to narrate, relate, or recount. In Hiligaynon it carries a further sense: to explain, to expound, to make clear, to relate distinctly.

That second meaning is the product. Extracting text from a book is a solved problem. Taking the chart, the diagram, the photograph — the parts a text extractor drops on the floor — and making them clear in words is what this application exists to do.

## 1. What Asoy is

Asoy is a Windows desktop application that converts books into text prepared for audiobook narration. It reads common ebook and document formats, extracts the text verbatim, and converts every non-text element (images, photographs, tables, diagrams, charts) into a written narrative description in its correct reading position, so a listener hears an account of the visual content rather than silence.

All processing happens on the user's machine. No book content, no page image, and no extracted text is transmitted anywhere.

## 2. Boundaries

These are architectural commitments, not preferences. Changing any of them is a redesign, not a feature.

- **No network egress of user content.** The application makes no outbound request carrying any part of a user's document. The only permitted network activity is the update check (see section 9).
- **No DRM circumvention.** Asoy processes files the user can already open. It contains no DRM-stripping code and loads no plugins that provide it. DRM-protected files are rejected at ingestion with a clear message.
- **No cloud fallback.** There is no degraded online mode. If the local model cannot run, the pipeline reports it rather than substituting a remote service.
- **Verbatim text.** Author text is transcribed, never summarised, paraphrased, corrected, or abridged. Only non-text blocks are described, and descriptions are always marked as such in the output.

## 3. System topology

```
                    +---------------------------------+
                    |     Asoy Desktop Shell (UI)     |
                    |  job queue . progress . review  |
                    +----------------+----------------+
                                     |
                    +----------------v----------------+
                    |      Conversion Orchestrator    |
                    |  tier detection . job lifecycle |
                    +----------------+----------------+
                                     |
        +----------------------------+----------------------------+
        |                            |                            |
+-------v--------+         +---------v---------+        +---------v---------+
| Format Router  |-------->|  Document Parser  |------->| Block Classifier  |
|                |         |     (Docling)     |        |                   |
| Calibre CLI    |         |                   |        | text | image |    |
| for MOBI/AZW3  |         | layout . reading  |        | table | chart     |
+----------------+         | order . tables    |        +---------+---------+
                           +---------+---------+                  |
                                     |                  +---------v---------+
                           +---------v---------+        |   Description     |
                           |    OCR Layer      |        |    Generator      |
                           | RapidOCR (ONNX)   |        |  Qwen3-VL-4B via  |
                           | CPU and GPU tiers |        |      Ollama       |
                           +---------+---------+        +---------+---------+
                                     |                            |
                                     +-------------+--------------+
                                                   |
                                      +------------v------------+
                                      |        Assembler        |
                                      |  Markdown emitter with  |
                                      |  delimited descriptions |
                                      +------------+------------+
                                                   |
                                      +------------v------------+
                                      |        Exporter         |
                                      |   .md (canonical)       |
                                      |   .txt (flattened)      |
                                      +-------------------------+
```

Everything inside this diagram runs on the user's machine. Ollama runs as a separate local process on `127.0.0.1`, installed and managed by the user.

## 4. Components

### 4.1 Desktop Shell

Windows desktop application built with pywebview: a Python process rendering an HTML, CSS, and JavaScript frontend in the system webview (Edge WebView2). Owns file selection, the job queue, progress reporting, per-description review, and settings. Holds no conversion logic. It drives the orchestrator and renders its state.

The shell and the pipeline run in one process, so progress and cancellation are direct calls rather than inter-process messages. See ADR-018.

Responsible for the first-run environment check (section 6) and for surfacing which hardware tier a job ran on, since that determines the quality the user should expect.

### 4.2 Conversion Orchestrator

The state machine for a conversion job. Detects the hardware tier once at startup, routes each input through the pipeline, tracks per-block progress, handles cancellation, and writes the job record used by the review UI and by support diagnostics.

Jobs are checkpointed per chapter. A cancelled or crashed job resumes from the last completed chapter rather than restarting the book — necessary because a long book on the CPU tier can take hours.

### 4.3 Format Router

Inspects the input and decides the path.

| Input | Path |
|---|---|
| EPUB, PDF, DOCX, PPTX, XLSX, HTML, images, plain text | Direct to Docling |
| MOBI, AZW, AZW3, FB2, LIT, PDB, RTF, ODT | Calibre `ebook-convert` then EPUB then Docling |
| DRM-protected (any format) | Rejected at ingestion |

Calibre is invoked as a subprocess over the command line. It is never linked, imported, or bundled — this keeps Asoy's Apache 2.0 license clear of Calibre's GPLv3. The subprocess boundary is a licensing boundary, not just a technical one, and must not be collapsed for convenience.

### 4.4 Document Parser

Docling. Produces the unified document representation: page layout, reading order, table structure, headings, and the position and extent of every non-text block. This is the component that makes reading order correct, which is the difference between a usable audiobook and a scrambled one.

Headings become Markdown headings and are the basis for chapter segmentation in the output.

### 4.5 OCR Layer

Engaged when a page carries no extractable text layer — scanned books, photographed pages, image-only PDFs.

Both tiers run **RapidOCR**, which executes the PP-OCR model family through a selectable inference backend. The tier changes the backend, not the engine:

- **CPU tier:** ONNX Runtime on CPU.
- **GPU tier:** ONNX Runtime with CUDA, falling back to CPU if the device is unavailable.

One engine across both tiers means OCR output differs by speed rather than by model, so a page that reads correctly on one tier reads correctly on the other. See ADR-019.

Pages that produce OCR output below the confidence floor are flagged in the job record and marked in the review UI rather than silently emitted. Handwritten content is not reliably recognised by either engine; this is a known limitation, documented in `SUPPORT.md`, not a defect to be filed.

### 4.6 Block Classifier

Takes the non-text blocks Docling identified and assigns each a type — photograph, illustration, table, diagram, chart — because the type determines the description prompt. A table is described as structured data read aloud; a chart is described by what it shows; a photograph is described by what is depicted. Using one generic prompt for all of them produces noticeably worse output.

Tables that Docling extracts cleanly bypass the vision model entirely and are rendered from their structure, which is both faster and more accurate than describing a picture of a table.

### 4.7 Description Generator

Qwen3-VL-4B at Q4 quantization, served by Ollama over the local HTTP interface.

Each block is cropped, passed to the model with a type-specific prompt, and returned as prose written to be *heard* — no bullet points, no markup, no "the image shows" preamble on every block. Output is length-bounded so a single diagram cannot produce three minutes of narration.

Each description carries a confidence signal derived from the model's response and the block's classification certainty. Low-confidence descriptions are surfaced for review rather than buried.

This component is where the product's name is earned. Everything upstream of it is assembly of existing open-source parts; the prompting, the type routing, and the length discipline here are the work.

### 4.8 Assembler

Emits the canonical Markdown. Author text is transcribed verbatim. Chapter structure is preserved as headings. Each description is wrapped in an explicit delimiter carrying its block type and confidence, so downstream consumers can switch voice, insert a pause, or skip descriptions entirely.

The delimiter is the output contract. It is a public interface — changing its shape is a breaking change and requires a major version bump.

### 4.9 Exporter

Writes two artifacts per job: the canonical `.md`, and a flattened `.txt` in which delimiters are removed and descriptions appear inline as plain prose. The `.txt` is a convenience for pipelines that cannot parse the delimiter; the `.md` is the source of truth and the only format from which other formats are derived.

SSML is not currently emitted. When added, it will be generated from the Markdown rather than produced by the pipeline directly.

## 5. Hardware tiers

Detected once at startup. Reported in the UI and recorded in every job record.

| Tier | Condition | OCR | Description model | Expected quality |
|---|---|---|---|---|
| GPU | NVIDIA device with 6 GB VRAM or more | RapidOCR, CPU backend today (see ADR-021) | Qwen3-VL-4B Q4 (~4 GB) | Full |
| CPU | No NVIDIA device, or under 6 GB VRAM | RapidOCR, CPU backend | Moondream 2 (~2 GB) | Reduced |

Tier detection queries the NVIDIA driver through NVML, not the installed inference libraries, because those report their own build configuration rather than the machine's hardware. See ADR-021.

**The quality difference is real and must be stated to the user, not hidden.** On the CPU tier, charts are described qualitatively — the shape and direction of the data — rather than numerically. Specific values are frequently missed. Photographs and illustrations degrade far less.

No tier above GPU is shipped. A 12 GB-class tier running an 8B model would produce better chart descriptions, but it is excluded because it cannot be tested on available hardware, and an untestable tier cannot be supported. See `DECISIONS.md`.

## 6. Environment dependencies

Two components are expected on the machine rather than shipped inside the application.

**Ollama** is a prerequisite, not a bundled component. The installer does not ship it, and Asoy does not manage its lifecycle.

**WebView2 Runtime** renders the interface. It is present by default on Windows 11 and on current Windows 10, and absent on older builds. Unlike Ollama it is redistributable, so the installer carries the evergreen bootstrapper and installs it silently when missing. The user is never asked to fetch it.

On first run, Asoy verifies in order: Ollama is installed; Ollama is reachable on its local port; the required model is pulled. Each failure produces a specific, actionable message and a link, not a generic error. This check re-runs at every startup, because users uninstall things.

This is the single largest source of setup friction in the product and the most common support contact. It is a deliberate trade: it hands model distribution, GPU detection, and quantization to a project that solves them well, at the cost of one setup step.

## 7. Where data lives

| What | Location | Lifetime |
|---|---|---|
| Source books | Wherever the user put them | Never moved, never copied, never modified |
| Working files (page images, crops) | Per-job temp directory | Deleted on job completion or cancellation |
| Output `.md` and `.txt` | User-chosen output directory | Permanent, user-owned |
| Job records (tier, timings, flags, errors) | Application data directory | Until the user clears them |
| Application logs | Application data directory | Rotated |

Job records and logs contain file paths and block-level metadata. They contain no book text and no page images. This matters because logs are what users attach to bug reports.

## 8. External dependencies

| Component | Role | License | Boundary |
|---|---|---|---|
| Docling | Document parsing | MIT | Library |
| Calibre `ebook-convert` | Kindle and legacy formats | GPLv3 | Subprocess only |
| RapidOCR | OCR, both tiers | Apache 2.0 | Library |
| PyTorch | Layout and table models, via Docling | BSD | Transitive, unavoidable |
| Qwen3-VL-4B | Descriptions, GPU tier | Apache 2.0 | Via Ollama |
| Moondream 2 | Descriptions, CPU tier | Apache 2.0 | Via Ollama |
| Ollama | Model runtime | MIT | Local HTTP, user-installed |
| pypdfium2 | PDF rendering | BSD/Apache | Library |
| pywebview | Desktop shell | BSD | Library |
| WebView2 Runtime | Frontend rendering, Windows | Microsoft, redistributable | System component |

This table lists the components Asoy depends on by name and by decision. It is not the full dependency tree, which runs to roughly 120 packages once Docling's model stack is resolved. The tree is what the quarterly license audit scans; this table is what the architecture commits to.

**PyMuPDF is prohibited.** It is AGPL and would relicense the application. If a transitive dependency pulls it in, that dependency is replaced, not accepted. This has caught other projects in this exact problem space.

Asoy's own code is Apache 2.0. The patent grant is the reason for Apache over MIT, given a stack built on models from Alibaba, Baidu, and IBM.

## 9. Network behaviour

Exactly one outbound request exists: the update check against the release endpoint. It carries the current version and nothing else — no document names, no usage data, no identifiers. It is disableable in settings, and disabling it disables no other functionality.

Ollama's model pull is a user-initiated action performed through Ollama, outside Asoy's process.

Any code path that would send document content anywhere is a defect of the highest severity, regardless of intent.

## 10. Failure surfaces

Documented here because these are where "looks finished" hides incompleteness.

- **Ollama absent or not running** — detected at startup and before each job; actionable message, no silent hang.
- **Model not pulled** — detected; the pull command is shown, not just named.
- **VRAM exhausted mid-job** — detected; the job falls back to the CPU tier and the output records that it did, so a quality drop is never unexplained.
- **DRM-protected input** — rejected at ingestion with an explanation of why, and no partial output.
- **Corrupt or malformed source file** — job fails with the file named; other queued jobs continue.
- **Calibre subprocess failure** — captured with its stderr, surfaced to the user, not swallowed.
- **OCR below confidence floor** — page flagged, emitted with a marker, listed in the review UI.
- **Model returns an empty or degenerate description** — block retried once, then emitted as an explicit placeholder rather than as silence, because silence in an audiobook is indistinguishable from the content not existing.
- **Disk exhaustion during a large job** — detected before writing; job pauses rather than producing a truncated file.
- **Crash mid-book** — chapter checkpoints survive; the job resumes rather than restarting.

## 11. Known architectural limitations

Stated here so they are not rediscovered as bugs.

- **Handwriting is not reliably recognised** by either OCR engine. This is a limitation of open-source OCR generally, not of the integration.
- **PDF is a lossy source format.** Conversion quality from PDF is materially worse than from EPUB, and heavily-designed PDFs (multi-column, sidebars, marginalia) produce reading-order errors that no downstream component can repair.
- **Chart descriptions are approximate.** Even on the GPU tier, a dense multi-series chart is described by shape more reliably than by value.
- **Windows only.** Not a portability limitation in the code so much as a support limitation: other platforms are not shipped because they cannot be tested.
- **Single-job execution.** Jobs run sequentially. Concurrent conversion would contend for the same GPU and produce worse throughput, not better.
- **Reading order in complex layouts** is Docling's judgement, and Asoy does not second-guess it. Where it is wrong, the output is wrong.

---

*Companion documents: `DECISIONS.md` (why the system is shaped this way), `RUNBOOK.md` (how to operate and release it), `SUPPORT.md` (stated limitations for users), `DATA.md` (what is held and where).*
