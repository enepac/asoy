# DECISIONS

**Project:** Asoy
**Document status:** Living record. Append-only.

> This file exists so that neither you nor an AI assistant re-litigates a settled question, and so that a choice which *looks* arbitrary later can be checked against why it was made.
>
> **Rules for this file.** Append new decisions; never delete old ones. When a decision is overturned, mark the original `Superseded by ADR-NNN` and leave its text intact — the reasoning that turned out to be wrong is the most useful thing in here. Every entry names what would reverse it, so a decision can be committed to now and revisited only when the world actually changes.

---

## ADR-001 - Local desktop application

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Asoy is a desktop application. Books are processed on the user's machine and never uploaded.

**Why.** Books are copyrighted material. The moment user-supplied books sit on a server, the project inherits DMCA exposure, storage costs that scale with file size, and a custodial obligation over people's personal libraries. Local execution removes all three at once. It also reduces `DATA.md` to almost nothing and turns the runbook into a release procedure rather than an uptime commitment — the difference between a project a solo maintainer can sustain and one that pages them at 2am.

**Rejected.**
- *Web app with server-side processing* — inherits every problem above.
- *Hosted API service* — same, plus abuse handling and per-request cost.
- *Hybrid (local processing, cloud vision only)* — superseded by ADR-002.

**Consequences.** Distribution and updates become harder: code signing, installer maintenance, no server-side hotfix. Usage telemetry does not exist unless deliberately built, and it is not built (ADR-013).

**Would reverse this.** Nothing short of a fundamental change in what the product does. This is the load-bearing decision the rest of the architecture rests on.

---

## ADR-002 - Fully local inference, no cloud calls at all

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** OCR and non-text description both run locally. There is no cloud vision model, no bring-your-own-key path, and no online fallback.

**Why.** Complete privacy with no asterisk, and no dependency on an external provider's pricing, availability, or terms. "Nothing leaves your machine" is a claim that survives scrutiny only if it is unconditional.

**Rejected.**
- *Frontier cloud vision for all non-text blocks* — best possible descriptions, but breaks the privacy claim and makes the product dependent on someone else's API.
- *Hybrid with bring-your-own-key* — was the original recommendation on quality grounds. Rejected because it still transmits page content, and because an API key requirement is a hard onboarding wall.
- *Hybrid via a hosted proxy* — turns a solo open-source project into a payments and abuse-handling business.

**Consequences.** This is the decision that costs the most quality. Local vision models describe a chart's *shape* far more reliably than its *values*. A frontier model would do materially better on dense diagrams. That gap is permanent under this decision and must be stated plainly to users rather than hidden (see `SUPPORT.md`).

**Would reverse this.** A local model that closes the chart-reading gap while still fitting consumer hardware. Not a user request for better quality — that request is expected and is not new information.

---

## ADR-003 - Two hardware tiers with runtime detection

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Two tiers, detected at startup: a GPU tier and a CPU fallback. Both are supported; the active tier is shown to the user and recorded in every job.

**Why.** A local application does not control the hardware it lands on. Hard-failing on an under-spec machine converts every such user into a support ticket answered personally. Two tiers is nearly free — Ollama serves either model through the same interface — so the real cost is documentation, not engineering.

**Rejected.**
- *CPU-only floor* — universally compatible, but gives up the GPU quality that most target users can actually reach.
- *Single GPU tier* — simpler, but unsupported users become support load.
- *Four or more tiers* — each tier is a quality baseline to test and a variable in every bug report.

**Consequences.** Every bug report must establish which tier the user was on. The incident template asks this first.

**Would reverse this.** Evidence that the CPU tier's output is bad enough that shipping it damages the project's reputation more than excluding those users would.

---

## ADR-004 - GPU tier is a 4B model, not 8B

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** The GPU tier runs Qwen3-VL-4B at Q4. No larger tier is shipped.

**Why.** Two reasons, and the second is the stronger one.

The hardware reason: an 8B model at Q4 occupies roughly 6 GB, which is the entire capacity of the development machine's RTX 3050 before the vision encoder, image tokens, or Windows desktop compositing take their share. It would fail to load or spill to system RAM.

The testability reason: **you can only ship what you can test.** A tier that cannot run on available hardware cannot be reproduced against a bug report, cannot be judged for description quality, and cannot be checked for regression. Shipping it would mean supporting output nobody has ever inspected.

**Rejected.**
- *Qwen3-VL-8B on the GPU tier* — does not fit the available card, and untestable.
- *An optional "advanced" tier for users with larger cards* — same testability objection; optional does not mean unsupported.

**Consequences.** Chart and diagram descriptions are weaker than the state of the art in local vision models. Users with 12 GB cards get no benefit from hardware they own.

**Would reverse this.** Access to a 12 GB-class card for development and testing. Hardware first, then the tier — not the other way around.

---

## ADR-005 - Markdown is canonical; plain text is derived

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** The pipeline emits Markdown as the source of truth, with chapter structure preserved as headings and every description wrapped in an explicit delimiter. A flattened `.txt` is generated from it.

**Why.** Audiobooks need chapter boundaries — for M4B chapter markers, for resumable playback, and above all so a user can regenerate one bad chapter instead of re-running an eight-hour job. Plain text destroys that structure irrecoverably.

The delimiter is the part that earns its keep. It lets a downstream pipeline switch to a secondary voice for descriptions, insert a pause, or skip them entirely. All three are things listeners want, and all three become impossible the moment descriptions are indistinguishable from the author's prose.

**Rejected.**
- *Single plain `.txt` with descriptions inline* — simplest, and forecloses every downstream option permanently.
- *SSML directly from the pipeline* — SSML is a family of engine-specific dialects, not one standard. Committing to one in v1 means rewriting the output layer for the first user with a different TTS. Better generated from Markdown later.
- *Chaptered text plus a JSON sidecar* — more machine-friendly and could carry confidence scores, but two files to keep synchronised and more complexity pushed onto the user's pipeline. Confidence can live in the delimiter's attributes instead.

**Consequences.** The delimiter format is a public interface (ADR-006).

**Would reverse this.** Nothing plausible. This is a one-way door that was deliberately walked through.

---

## ADR-006 - The description delimiter is a public interface

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** The delimiter's shape and attributes are treated as a published contract. Changing it is a breaking change requiring a major version bump.

**Why.** Users will build TTS pipelines that parse it. Silently restructuring it breaks their tooling with no warning, which is the fastest way for a small open-source tool to lose the users who cared most.

**Rejected.**
- *Treating output format as an implementation detail* — convenient for the maintainer, hostile to the people integrating with it.

**Consequences.** Output-layer refactors are constrained. Adding attributes is fine; renaming or restructuring is not, without a major version.

**Would reverse this.** Nothing. Interfaces are promises.

---

## ADR-007 - Windows only

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Windows is the only shipped platform. macOS and Linux builds are not produced.

**Why.** The same testability principle as ADR-004. A macOS Metal inference failure cannot be debugged on a machine that does not exist. Shipping three platforms as one maintainer means every bug report arrives with an uncontrolled platform variable.

**Rejected.**
- *Cross-platform via Tauri or Electron* — technically achievable, operationally untestable at current resources.
- *Linux only, source install* — smaller audience, and does not match where the maintainer works.

**Consequences.** Most of the potential open-source audience is excluded. Expect recurring requests for macOS builds; the answer is documented here rather than improvised each time.

**Would reverse this.** Access to a macOS machine for testing, plus a contributor willing to own the platform. Not a volume of requests.

---

## ADR-008 - Ollama is a prerequisite, not a bundled component

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** The installer does not ship a model runtime. It verifies Ollama is installed, reachable, and has the required model pulled, and guides the user through each missing step.

**Why.** Bundling PyTorch, OCR models, and a VLM produces a multi-gigabyte installer that must be rebuilt and re-signed on every dependency update, and installers that size fail in ways that are miserable to diagnose remotely. Depending on Ollama hands model distribution, GPU detection, quantization, and updates to a project that already solves them well.

**Rejected.**
- *Bundle everything* — better first-run UX, at the cost of an installer that becomes the project's main maintenance burden.
- *Document Ollama in the README and check nothing* — guarantees that setup failures arrive as bug reports.

**Consequences.** This is the largest source of onboarding friction and the most common support contact. The first-run environment check is a feature that must be built well, not a README section.

**Would reverse this.** Ollama becoming unmaintained or changing its interface in a way that breaks the integration.

---

## ADR-009 - Docling as the core parser, not Marker

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Docling is the document parsing layer.

**Why.** Licensing. Docling's code is MIT and it is hosted under the LF AI & Data Foundation, which means permissive terms and governance that will not change under one maintainer's commercial pressure. It covers PDF, EPUB, DOCX, images, and more in one library, with layout and reading-order analysis.

**Rejected.**
- *Marker* — benchmarks better on extraction accuracy, but its model weights carry a modified Open RAIL-M license with revenue and funding thresholds, and commercial self-hosting requires a separate license. Fine for a hobby project, a renegotiation for anything that grows.
- *Building on raw PDF libraries* — reading-order analysis is the hard part and is not worth reimplementing.

**Consequences.** Extraction accuracy is somewhat below the best available open-source option.

**Would reverse this.** Docling stagnating while a permissively-licensed alternative pulls meaningfully ahead.

---

## ADR-010 - Calibre is invoked as a subprocess only

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Kindle and legacy formats are handled by calling Calibre's `ebook-convert` over the command line. Calibre is never linked, imported, or bundled into the application.

**Why.** Calibre is GPLv3. Asoy is Apache 2.0 (ADR-012). The command-line boundary is what keeps those compatible. This is a licensing boundary wearing the costume of a technical one, and collapsing it "for convenience" would relicense the project.

**Rejected.**
- *Linking or vendoring Calibre* — relicenses Asoy under GPLv3.
- *Dropping MOBI/AZW3 support* — Calibre is the only serious option for these formats, and Kindle files are a large share of what people own.

**Consequences.** Calibre must be present for those formats. Subprocess failures need explicit capture and surfacing, since a silently swallowed stderr is an unexplainable bug.

**Would reverse this.** Nothing. This is a legal constraint, not a preference.

---

## ADR-011 - PyMuPDF is prohibited

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** PyMuPDF may not appear in the dependency tree, directly or transitively. pypdfium2 is used for PDF rendering.

**Why.** PyMuPDF is AGPL. Its presence would relicense the application, and AGPL's network clause is not something to inherit accidentally. It has caught other projects in exactly this problem space, because it is the most convenient PDF library in Python and therefore the most commonly pulled in without checking.

**Rejected.**
- *Using PyMuPDF and relicensing under AGPL* — would deter the integrators this project wants.

**Consequences.** Any dependency that pulls in PyMuPDF is replaced, not accepted. This needs a check in CI, not a note in a document.

**Would reverse this.** Nothing.

---

## ADR-012 - Apache 2.0, free and open source

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Asoy is free and open source under Apache 2.0, in a public repository. No paid tier, no license keys, no freemium unlock.

**Why.** Apache over MIT specifically for the express patent grant, which matters when the stack is built on models released by Alibaba, Baidu, and IBM. MIT is silent on patents. Apache also matches most of the dependency stack, so there is no compatibility analysis to redo later.

Open source over paid because the whole dependency stack is free and open. A paid closed-source wrapper would have to survive the question "why not just run Docling myself?" — a real business, but a real risk, and one that adds payment processing, license enforcement, refunds, and tax handling to a solo maintainer's load.

**Rejected.**
- *MIT* — permissive but patent-silent.
- *One-time paid license* — viable given zero marginal cost per user, but adds a payments business.
- *Free core with paid unlock* — requires a license-key subsystem and creates a new class of support ticket.
- *GPL* — would deter integration into other tooling, which is where this project's value compounds.

**Consequences.** No revenue. Support is unbounded and unpaid, and the maintainer is the only person answering until contributors appear.

**Would reverse this.** Support load exceeding what one person can carry, making some form of funding necessary. Note that relicensing after contributors arrive requires their agreement — this is closer to a one-way door than it looks.

---

## ADR-013 - No telemetry, one outbound request

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** The only network request the application makes is a version check. It carries the current version and nothing else, and it is disableable.

**Why.** A privacy-first local application that phones home about usage undermines its own central claim. The absence of telemetry is a feature, and it must be verifiable by anyone reading the source — which, being open source, they can.

**Rejected.**
- *Anonymous usage analytics* — would genuinely help prioritise work, and is incompatible with the promise made in ADR-002.
- *Crash reporting to a remote endpoint* — same objection. Crash data stays local and is attached by the user if they choose.

**Consequences.** There is no data on which formats users actually convert, which tier they run, or where they fail. Prioritisation depends on what people report, which is a biased sample.

**Would reverse this.** Nothing short of explicit, off-by-default, per-user opt-in — and even then the burden of proof is high.

---

## ADR-014 - No DRM circumvention, ever

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Asoy contains no DRM-stripping code and loads no plugins that provide it. DRM-protected files are rejected at ingestion with an explanation.

**Why.** A book-conversion tool that strips DRM is a legal problem regardless of intent, and would make the project undistributable and uncontributable-to. Calibre's own conversion tools do not strip DRM either; that is plugin territory, and it stays out.

**Rejected.**
- *Silently failing on DRM files* — users cannot tell a bug from a boundary.
- *Documenting a DRM-removal workaround* — provides the circumvention by other means.

**Consequences.** A visible share of users' libraries will not convert. This must be a documented limitation in `SUPPORT.md` with a clear explanation, so the answer is written once rather than improvised per ticket.

**Would reverse this.** Nothing.

---

## ADR-015 - Chapter checkpointing

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** Jobs checkpoint at chapter boundaries. A crashed or cancelled job resumes rather than restarting.

**Why.** A full book on the CPU tier runs for hours. Losing that to a crash or a laptop lid is the kind of experience that produces an ex-user, and the state required is small — a chapter index and a partial output file.

**Rejected.**
- *No checkpointing in v1* — simpler, and gambles the worst-case user experience on nothing going wrong across a multi-hour job.
- *Per-block checkpointing* — finer granularity, considerably more state, marginal benefit over per-chapter.

**Consequences.** Job state must be persisted, versioned, and invalidated when the source file changes.

**Would reverse this.** Evidence that jobs are short enough that a restart is not costly — which would mean the performance picture changed substantially.

---

## ADR-016 - Failed descriptions emit a placeholder, never silence

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** When the model returns an empty or degenerate description, the block is retried once and then emitted as an explicit placeholder marking that a visual element could not be described.

**Why.** In an audiobook, silence where a description should be is indistinguishable from the content not existing. The listener has no way to know something was missed. An explicit placeholder is worse prose and better information.

**Rejected.**
- *Omit failed blocks silently* — cleaner output, and lies to the listener by omission.
- *Fail the whole job* — disproportionate; one bad diagram should not cost a book.

**Consequences.** Output can contain placeholders users find intrusive. They are listed in the review UI so a user can supply their own text.

**Would reverse this.** A user-configurable preference could soften this, but silent-by-default stays wrong.

---

## ADR-017 - The name

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** The project is named **Asoy**.

**Why.** *Asoy* is Cebuano and Hiligaynon. In Cebuano it means to narrate, relate, or recount; in Hiligaynon it carries the further sense of explaining, expounding, and making clear. That second meaning names the differentiator precisely: the product does not merely transcribe a book, it makes its visual content clear in words. It is four letters, unambiguous to spell, and drawn from a language the maintainer has a claim to.

**Rejected.**
- *Ekphra* — from *ekphrasis*, and the strongest candidate on meaning. Rejected on collision: ekphra.com is an active platform for artists and poets built on the same Greek root, launching in August 2026. Same name, adjacent concept, existing brand.
- *Narrata, Recto, Legenda, Sonorem, Depictor* — all workable; none carry the "make clear" sense or a personal claim.

**Consequences.** International users will need the etymology explained. One line in the README covers it.

**Would reverse this.** A trademark conflict surfacing later. Verify the name against GitHub, PyPI, and a basic trademark search before the repository goes public.

---

## ADR-018 - Desktop shell is pywebview, not a native toolkit

**Date:** 2026-08-09 · **Status:** Accepted

**Decision.** The desktop shell is pywebview: a Python process rendering an HTML, CSS, and JavaScript frontend inside the system webview. On Windows this is the Edge WebView2 runtime.

**Why.** The conversion pipeline is Python by necessity, since Docling, PaddleOCR, Tesseract, and the Ollama client all live there. pywebview keeps the UI in that same process, so progress reporting, cancellation, and mid-job tier fallback are ordinary function calls rather than messages across a bridge between two languages. It is BSD licensed, which is the cleanest fit alongside Apache 2.0, and it does not bundle a renderer, so the frozen executable stays small.

The review screen is the demanding surface: a long list of cropped images paired with editable descriptions and confidence flags. CSS handles that layout with less effort than a native widget toolkit, and the styling work is transferable if the frontend is ever reused.

**Rejected.**
- *PySide6 (Qt for Python)* - one language, mature, strong model and view classes for long lists. Rejected on two grounds: LGPLv3 adds a relinking obligation that conflicts with one-file packaging, and a default-styled Qt application needs substantial work to look current.
- *Tauri* - smallest binary and the best-looking result, but adds Rust and a separate frontend toolchain, and runs Python as a sidecar process with an IPC bridge the maintainer owns.
- *Electron* - familiar web stack, same sidecar and bridge problem as Tauri, with a much heavier install.

**Consequences.** WebView2 Runtime becomes a second environment prerequisite alongside Ollama. It is preinstalled on Windows 11 and current Windows 10, absent on older builds, and can be carried by the installer's bootstrapper. The frontend is HTML and JavaScript, so the project now spans two languages even though it runs as one process, and frontend assets must be packaged with the application.

**Would reverse this.** The Python to DOM bridge proving too slow or too fragile for the review screen at realistic sizes, on the order of several hundred descriptions in one book. Measure before switching, and record the measurement.

---

*Companion documents: `ARCHITECTURE.md` (what the system is), `RUNBOOK.md` (how to operate it), `SUPPORT.md` (what users are told), `DATA.md` (what is held).*
