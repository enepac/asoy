# DECISIONS

**Project:** Asoy
**Document status:** Living record. Append-only.

> This file exists so that neither you nor an AI assistant re-litigates a settled question, and so that a choice which *looks* arbitrary later can be checked against why it was made.
>
> **Rules for this file.** Append new decisions; never delete old ones. When a decision is overturned, mark the original `Superseded by ADR-NNN` and leave its text intact — the reasoning that turned out to be wrong is the most useful thing in here. Every entry names what would reverse it, so a decision can be committed to now and revisited only when the world actually changes.
>
> **Amendments.** An ADR that defines a specification may be amended in place when the amendment is purely additive and no consumer depends on the spec yet. Mark the amendment with its date, leave the original text intact, and point to it from the section it changes. Anything that changes, narrows, or reverses a decision gets a new ADR instead, however small. The append-only rule exists so that reasoning which turned out wrong is never erased, and an additive amendment erases nothing.

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

## ADR-019 - One OCR engine across both tiers

**Date:** 2026-08-10 · **Status:** Accepted. Supersedes the engine choice in ADR-003, whose two-tier structure is unchanged.

**Decision.** Both tiers run RapidOCR. The hardware tier selects the inference backend, not the engine. Tesseract and PaddleOCR are removed.

**Why.** Discovered while resolving dependencies rather than while planning. RapidOCR arrives with Docling at no additional cost and executes the same PP-OCR model family that PaddleOCR uses, through ONNX Runtime instead of the PaddlePaddle framework. The models are identical, so the accuracy argument for PaddleOCR evaporates once the runtime is interchangeable.

Removing the other two engines removes four costs at once. Tesseract needs a system binary install, which would have been a third setup prerequisite with no bootstrapper, in a product whose largest support cost is already setup friction (ADR-008). PaddleOCR pulls in 28 packages including the PaddlePaddle framework. Those packages brought the only two GPL-family licenses in the tree, crc32c and python-bidi, both LGPL, which would have needed the same packaging analysis that rejected PySide6 in ADR-018. And paddlex capped numpy below 2.4, which constrained the base install even when the optional extra was not synced.

A single engine also means output differs between tiers by speed, not by model. A page that reads correctly on one tier reads correctly on the other, which removes a variable from every bug report.

**Rejected.**
- *Keeping Tesseract for CPU and PaddleOCR for GPU* - the specified design, written before the dependency tree was resolved. Costs a system prerequisite, 28 packages, two LGPL dependencies, and a numpy ceiling, to run models already present.
- *RapidOCR for both tiers with PaddleOCR as an optional extra* - keeps the numpy coupling and the LGPL packages alive for a fallback that may never be used.

**Consequences.** ONNX Runtime inference has not been benchmarked against native PaddlePaddle on the development card. Accuracy should be identical since the models are, but throughput is unmeasured. PyTorch is in the tree for Docling's layout models, but the wheel that resolves from PyPI on Windows is the CPU-only build. A CUDA-accelerated OCR backend would need onnxruntime-gpu, which is a separate package and not currently installed. See ADR-021.

**Would reverse this.** A measured benchmark showing the ONNX path is materially slower on a full book on 6 GB-class hardware. Measure before switching, and record the measurement.

---

## ADR-020 - PyTorch is an unavoidable dependency, amending ADR-008's rationale

**Date:** 2026-08-10 · **Status:** Accepted. Amends the reasoning in ADR-008; the decision itself stands.

**Decision.** PyTorch is accepted as a hard, non-optional dependency of the base install, at roughly 470 MB.

**Why.** Docling's layout analysis and table structure models are PyTorch. There is no configuration in which Docling parses a PDF correctly without it, and layout plus reading order is the component ADR-009 selected Docling for. The dependency is not a choice that was made; it is a consequence of one that was.

**What this amends.** ADR-008 declined to bundle a model runtime partly on the grounds that shipping PyTorch and OCR models would produce a multi-gigabyte installer. That reasoning is now partly wrong: most of that weight is in the base install regardless of whether Ollama is bundled. The decision to keep Ollama external still holds, but on the remaining grounds, that Ollama solves model distribution, GPU detection, quantization, and updates well, and that bundling it would mean re-releasing Asoy on every model update.

**Consequences.** The installer will be large. Installer size is therefore a stated expectation in SUPPORT.md rather than a defect, and any future work on reducing it starts from the Docling model stack, not from Ollama.

**Would reverse this.** Docling offering a layout backend that does not require PyTorch, or a decision to replace Docling, which would reopen ADR-009.

---

## ADR-021 - Tier detection queries the driver, not torch

**Date:** 2026-08-10 · **Status:** Accepted. Refines ADR-003's detection mechanism; the two-tier structure is unchanged.

**Decision.** Hardware tier detection uses NVML through nvidia-ml-py. It does not use torch.cuda.is_available().

**Why.** The two questions are different, and only one of them is the question ADR-003 asks. torch.cuda.is_available() reports whether the installed torch build was compiled with CUDA support. The tier needs to know whether the machine has a capable GPU. On the development machine those answers diverged: an RTX 3050 with 6144 MiB and a working driver classified as CPU tier, because the torch wheel that resolves from PyPI on Windows is CPU-only.

That divergence is not a development-machine quirk. Every user installing Asoy today would have received the CPU-only wheel, so the GPU tier was unreachable for everyone regardless of hardware. NVML queries the driver directly and answers the hardware question correctly.

**What the tier actually governs, and what it does not.** The description model is selected inside Ollama, a separate process performing its own GPU detection, so it benefits from the GPU tier independently of anything Asoy installs. That is where ADR-002 and ADR-004 locate the quality difference, and it works. Docling's layout and table models run on the CPU-only torch build, and RapidOCR runs on CPU ONNX Runtime. So the GPU tier currently delivers better descriptions but not the faster conversion that ARCHITECTURE section 5 implies.

**Rejected.**
- *Installing a CUDA torch build from the PyTorch index* - would fix detection and accelerate Docling's layout pass, at roughly 2.5 GB instead of 470 MB. Rejected for now because it contradicts the installer-size expectation stated in SUPPORT.md and ADR-020 on the day both were written, and because no conversion pipeline exists yet to measure whether the layout pass is the dominant cost.
- *An optional CUDA extra* - same objection at present, and a reasonable addition once there is a benchmark to justify it.
- *Dropping the GPU tier* - the description-quality difference is real and is delivered today.

**Consequences.** Known gap: GPU-tier conversion speed is not yet what the architecture describes. Closing it means adding onnxruntime-gpu for OCR, which is the cheaper and more useful half, and possibly a CUDA torch build for layout, which is the expensive half. Neither should be decided without a measured conversion.

**Would reverse this.** Nothing reverses using NVML for detection; it is simply the correct question. The related speed gap is addressed by adding acceleration packages, which is a separate decision resting on a benchmark.

---

## ADR-022 - The assembler builds Markdown from raw text, not from Docling's exporter

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** The parser carries each item's raw text and the assembler composes the Markdown itself. It does not call Docling's `export_to_markdown()`.

**Why.** Invariant 3. Docling's exporter escapes some Markdown metacharacters and not others: a passage containing `_word_` comes back as `\_word\_`, while `*word*` is passed through untouched. Neither behaviour is wrong for a general exporter, but the pair is inconsistent, and both are decisions about the author's characters that Asoy has not made.

The inconsistency is the part that matters. Escaping everything would at least be reversible. Escaping half means one emphasis marker survives into the output as literal backslashes a naive consumer will read aloud, and the other silently becomes emphasis. Author text has to be one thing or the other, chosen deliberately, and the exporter chooses for us.

Composing the Markdown ourselves also keeps the structural characters countable. The only characters Asoy adds are the `#` of a heading and the blank line between blocks, which is what makes the parse-to-emit chapter assertion meaningful.

**Rejected.**
- *Call `export_to_markdown()` and post-process* - unescaping someone else's escaping is guesswork the moment the author writes a real backslash.
- *Escape everything ourselves* - defensible, and it is the obvious future change, but it is an output-contract decision that belongs with the delimiter work in ADR-006 rather than being settled by a parser convenience.

**Consequences.** Author text is emitted with no escaping at all today. A paragraph that legitimately begins with `#` or `>` will be read as structure by a strict Markdown parser. This is a known, unhandled edge and is not yet decided; it should be settled alongside the delimiter, since both concern how the output distinguishes Asoy's characters from the author's.

**Would reverse this.** Docling gaining a documented, consistent no-escape or full-escape mode, or the delimiter work settling on an escaping policy that the assembler should apply uniformly.

---

## ADR-023 - ODT goes direct to Docling; RTF stays behind the Calibre boundary

**Date:** 2026-08-10 · **Status:** Accepted. Amends the routing table in ARCHITECTURE section 4.3. ADR-010 is unchanged.

**Decision.** ODT routes directly to Docling. RTF continues to route through Calibre's `ebook-convert`, alongside MOBI, AZW, AZW3, FB2, LIT, and PDB.

**Why.** ADR-010's subprocess boundary exists to reach formats only Calibre can read. It is a cost, not a default. It makes a GPLv3 program a prerequisite the user has to find and install, which is the same friction ADR-008 accepted reluctantly for Ollama and named as the product's largest support burden. It sends the book through an intermediate EPUB, so what Docling parses is Calibre's rendering of the file rather than the file. And it is a licensing boundary that has to be maintained forever. A format Docling reads itself should not pay any of that.

Docling reads ODT natively through its OpenDocument backend, at MIT (ADR-009). Routing ODT to Calibre bought nothing in exchange for all three costs. The original routing table appears to have grouped ODT with RTF as "office and legacy formats" rather than by what Docling can actually read, which is the only distinction that matters here.

RTF is a different case, and the difference is simply that Docling cannot read it. Docling 2.118.1 has no RTF member in `InputFormat`, no RTF backend, and no optional extra that supplies one; its OpenDocument formats are `odt`, `ods`, and `odp` only. Checked against the installed version rather than assumed. RTF therefore stays on Calibre for exactly the reason MOBI does.

**Why the boundary still holds for MOBI, AZW, AZW3, and FB2.** Restated so this is not read as an erosion of ADR-010. Docling has no backend for any of them. The Kindle formats are Amazon's, documented by reverse engineering rather than by specification, and Calibre's readers are the only serious implementations of them; FB2 is niche enough that the same is true in practice. Writing our own readers to avoid the prerequisite would mean reimplementing working software for licensing hygiene we already have a correct answer for. ADR-010's reasoning is untouched: those formats need Calibre, Calibre is GPLv3, and the command line is what keeps Apache 2.0 intact. This decision only stops sending that boundary work it was never needed for.

**Rejected.**
- *Route RTF direct as well* — the instruction that prompted this ADR assumed Docling handled both formats natively. It does not handle RTF, and routing it direct would fail every RTF file at parse time, converting a working path into a broken one.
- *Keep ODT on Calibre for consistency* — consistency with nothing. The routing table's actual principle is "what Docling can read, Docling reads", and ODT was an unexplained exception to it.
- *Add `odfdo` as an optional extra rather than a dependency* — ODT would then fail at parse time on a default install, which is a worse failure than the one being removed.

**Consequences.** Docling's OpenDocument backend requires `odfdo`, which the base `docling` package does not install. It joins the dependency manifest at 3.24.3, Apache-2.0, whose only runtime dependency is `lxml` (BSD-3-Clause), already present. Nothing GPL-family or AGPL enters, so invariants 6 and ADR-011 are unaffected. CLAUDE.md section 5 lists the dependency manifest as ask-first; this addition is recorded here and raised rather than made quietly.

ODT conversions no longer require Calibre. README already listed Calibre as needed for MOBI, AZW, AZW3, and FB2 only, so it becomes accurate rather than needing a correction.

An ODT converted under the old routing is not reproducible under the new one. The output comes from the ODT rather than from Calibre's EPUB rendering of it, which is the point, but it is a change in output for identical input.

Password-protected ODF is not detected by the ingestion DRM check, which reads zip flag bits and EPUB and MOBI markers. An encrypted ODT now reaches Docling and fails there with a parse error naming the file. That is loud rather than silent, so invariant 7 holds, but it is a newly reachable gap in the invariant 2 check and should be closed when ODF encryption markers are added to the inspector.

**Would reverse this.** Docling dropping its OpenDocument backend, or `odfdo` relicensing to a copyleft license. RTF moves to the direct path if Docling gains an RTF backend, which needs no new decision — it is the same rule applied to a changed fact.

---

## ADR-024 - The parser releases Docling's file handle through a private attribute

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** `asoy.parser.parse` reaches into `result.input._backend` and calls its `unload()` before returning, so the source file is closed by the time the parse completes. The call is guarded: if the attribute is absent or the call raises, the parse still succeeds.

**Why.** Docling does not close the file. Its `SimplePipeline` — which serves EPUB, DOCX, ODT, and the other declarative formats — inherits the base pipeline's no-op `_unload`, and `DocumentConverter` only unloads a backend when the pipeline failed to start. So on the success path the backend's open `ZipFile` outlives the conversion and the file stays open until garbage collection happens to collect it.

On Windows an open handle prevents deletion. That turns a library detail into a defect at the worst possible moment: the intermediate EPUB on the Calibre path lives in the job's temp directory, and removing that directory is the last thing a job does (ARCHITECTURE section 7). The conversion succeeded, the output was written and verified, and then cleanup raised `PermissionError`. Non-deterministically, too — whether it failed depended on whether a garbage collection had happened to run, which is the kind of intermittent failure that costs far more to diagnose than to prevent.

There is no public API for this. `ConversionResult` exposes no close, no release, and no context manager, and the pipeline that would have called `unload` for us is the one that does not. The alternative to reaching for the private attribute is leaking one file handle per conversion for the life of the process, and leaving book files open is not a defensible position for an application whose stated contract is that source books are never moved, copied, or modified.

**Rejected.**
- *Rely on garbage collection* — the observed failure. CPython's refcounting closes it eventually, but "eventually" is not a guarantee the cleanup step can be written against.
- *Delete the temp directory with `ignore_cleanup_errors=True`* — turns a visible failure into book content left in the temp directory, silently, which is worse against `DATA.md` than the error was.
- *Copy the intermediate somewhere Asoy controls and never delete it* — same objection, plus it duplicates the user's book on disk.
- *Force a `gc.collect()` before cleanup* — works by accident, explains nothing, and would be deleted by the next reader as superstition.
- *Patch Docling and wait for the release* — the right long-term move and no help today. Worth doing upstream; this ADR does not depend on it landing.

**Consequences.** Asoy now depends on a private attribute of a third-party library, which is exactly the kind of coupling a dependency upgrade breaks without warning. The failure mode if Docling renames or restructures `input._backend` is a silent return to the old behaviour rather than an exception, because the call is guarded — so the guard that matters is the test, not the code.

**The guard.** `tests/test_pipeline.py::test_parse_does_not_hold_the_file_open` parses a book and then deletes it. On Windows that fails with `PermissionError` if the handle is still open, which is what it did before this change. `tests/test_calibre.py::test_the_intermediate_epub_does_not_outlive_the_job` covers the same defect from the other end, asserting the temp directory is gone after a Calibre-path conversion. A Docling upgrade that breaks the private access fails both. Dependency upgrades should be treated as touching this ADR.

**Would reverse this.** Docling exposing a public way to release the backend — a `close()`, a context manager on `ConversionResult`, or `SimplePipeline` unloading the way `PaginatedPipeline` already does. Switch to it and delete `_release`'s reach into the private attribute the same day; the tests above will confirm the replacement works before the old code comes out.

---

## ADR-025 - The description delimiter is an HTML comment fence

**Date:** 2026-08-10 · **Status:** Accepted. Settles the shape ADR-006 reserved, and closes the open edge left by ADR-022.

**Decision.** The delimiter is a pair of HTML comments. Three markers exist and no others.

A document header, the first line of every `.md`:

```
<!-- asoy:document version="1" tier="gpu" model="qwen3-vl:4b" -->
```

A description:

```
<!-- asoy:description type="chart" confidence="0.82" status="ok" -->
Description prose here.
<!-- /asoy:description -->
```

Author text needing disambiguation:

```
<!-- asoy:text -->
# Author's own hash, not a chapter heading.
<!-- /asoy:text -->
```

`type` is one of `photograph`, `illustration`, `table`, `diagram`, `chart`, `unknown` — a closed set for v1, to which adding a member is a MINOR release. `confidence` is 0.00 to 1.00 at two decimals. `status` is `ok` or `failed`. All three are always present, always in that order, and a parser may rely on it. *(A fourth attribute was added the same day — see the amendment at the end of this entry.)*

**Why this shape.** Four properties, and it is the only candidate that has all four.

It is **valid CommonMark**, so it survives every Markdown parser rather than depending on one. It is **invisible when rendered**, so the `.md` reads as a clean book to a human opening it in any viewer — the delimiter costs the primary artifact nothing. It is **trivially strippable** for the flattened `.txt`, which is a line-oriented transformation rather than a parse. And its **attributes extend without a major version**: a new attribute is additive, which is exactly the axis ADR-006 needs to stay cheap, since the attributes are where confidence, provenance, and future signals will accumulate.

**The decisive argument is collision.** Everything above is a convenience. The requirement is that a book cannot forge a delimiter — that no arrangement of the author's own text can produce something a downstream pipeline reads as Asoy's description, because that would let a book fabricate content that gets read in a different voice or skipped entirely. Author text will essentially never contain the string `<!-- asoy:description`, and where it does, the block is wrapped in a text fence and the parser treats a text fence's body as opaque. That is proved rather than asserted: `tests/test_fences.py` renders each of Asoy's own markers as author text and requires them back as author text.

**On confidence.** It is an uncalibrated heuristic derived from the model's response and the block's classification certainty. It orders descriptions by how much they are worth a human's attention. **It is not a probability**, it has never been calibrated against ground truth, and 0.80 does not mean eight in ten. Stated here and in ARCHITECTURE 4.8 because a two-decimal number in a machine-readable attribute invites exactly the reading it does not support.

**Rejected.**
- *Fenced code blocks with an info string* — `​```asoy-description type="chart"`. Unambiguous and easy to parse, and it renders as a code block: monospaced in every viewer, and read aloud as code by a pipeline that does not know better. The description is prose and must look like prose.
- *MyST-style directive containers* — `:::{asoy-description}`. Expressive and well-specified, and not CommonMark. In any plain Markdown viewer the colons appear as literal text, which puts Asoy's syntax in front of a reader in the one artifact meant to read as a book.
- *A sentinel character or unusual Unicode delimiter* — compact, and it collides. The whole argument above rests on a delimiter no book will contain by accident.
- *A JSON sidecar carrying descriptions by offset* — rejected in ADR-005 already, and offsets into a file the user may edit are fragile in a way inline markers are not.

**The escaping policy, which closes ADR-022's open edge.** **Asoy never modifies a byte of author text, and never escapes it.** ADR-022 left this unsettled and named escaping-everything as the obvious future change. It is not the change that gets made. A backslash inserted to tame a Markdown metacharacter is a character a naive text-to-speech engine reads aloud, which turns a rendering ambiguity into an audible defect — the same reasoning that rejected code fences above.

Where a block would be misread as structure, it is wrapped in `asoy:text` instead. The fence is used only where it is needed, so ordinary prose is unadorned; every line of a block is checked rather than only the first, because a heading or a list marker can interrupt a paragraph.

Only two things in an emitted file are Asoy's characters: the markers, and the `#` of a heading. That is what keeps the parse-to-emit chapter assertion meaningful, and it is now checkable by parsing the artifact rather than by scanning it for lines starting with a hash.

**Consequences.** There is one case the format cannot represent: author text containing a line that is exactly `<!-- /asoy:text -->`. It cannot be escaped, by the rule above, and it cannot be wrapped, because it would close its own fence. Asoy raises and writes nothing rather than emitting a file that misparses itself. This requires a book to contain Asoy's closing marker verbatim on its own line; it is recorded here because a silent corruption would be far worse than a loud refusal, not because it is expected.

The header carries `tier` and `model` on every job, which makes invariant 8 a property of the output rather than only of the UI: a file that reads differently from another can always be traced to what produced it.

The `.md` and `.txt` are both rendered from one document object, and the module that emits the format also parses it. A round-trip test is therefore the primary guard: emit, parse, and require the result identical.

**Would reverse this.** Nothing about the shape, short of a major version. Attribute additions are expected and are the mechanism this format was chosen for. If a fourth marker is ever needed, it takes the same `<!-- asoy:name -->` form, and the fencing rule already treats any `<!-- asoy:` line in author text as needing a fence, so text emitted today cannot forge a marker invented tomorrow.

### Amendment, 2026-08-10 — the `source` attribute

*The text above is left as written. This is an addition to it, made the same day, and the original wording is kept because the gap it left is the useful part.*

**A fourth attribute, `source`, valued `structure` or `model`.** Attribute order becomes `type`, `confidence`, `status`, `source`, all four always present.

```
<!-- asoy:description type="chart" confidence="0.82" status="ok" source="model" -->
```

**Why.** The decision above rendered a cleanly extracted table from its cells at `confidence="1.00"`, on the reasoning that nothing about it was uncertain. That is sound and it made 1.00 mean two different things: a table read straight off its own structure, and a vision model that happened to score well. A consumer sorting by confidence to decide what a human should review would have mixed them, and the ordering would have been silently wrong rather than visibly wrong.

`source` says which path produced the description, which is what makes `confidence` comparable at all.

**What `source` means, stated plainly because the obvious reading is the wrong one.** It names **the route the description was meant to come from, not who typed the characters in the body**. A `failed` description carries `source="model"` even though the placeholder text in it was written by Asoy and no model ran at all — the model path is the one that was responsible for that block and did not deliver.

**`status` and `source` are read together.** Neither is complete alone:

| `status` | `source` | What it means |
|---|---|---|
| `ok` | `structure` | Read directly off the block's own structure. Exact. Nothing to review |
| `ok` | `model` | A vision model described it. An estimate; `confidence` orders these for review |
| `failed` | `model` | The model path was responsible and produced nothing usable. The body is a placeholder |

A consumer deciding whether re-running a block could help needs both: `status` says what happened, `source` says where it was meant to come from, and `failed` plus `model` is the combination worth another attempt.

The fourth combination, `failed` with `structure`, is legal in the format and Asoy never emits it. A table whose structure does not extract cleanly is not a dead end — it falls through to the model path, and so it is `source="model"` like any other picture. Nothing became responsible for it that then failed.

This is additive, so it is MINOR-compatible under ADR-006, and it costs nothing today because no consumer exists. That is precisely why it is worth doing now: the same fix after someone has integrated is a coordination problem rather than an edit.

**On the header's `version`.** It stays at `1`. It tracks breaking changes to the format, not additive ones — a parser written against the three-attribute form would fail on the fourth, but no such parser exists, and bumping the version for every addition would make it a change counter rather than a compatibility signal.

**Rejected.**
- *Give structural tables a lower confidence to keep the number's meaning uniform* — would encode a doubt that does not exist, and make the review UI surface correct tables for checking.
- *A third value for placeholders, `source="placeholder"`* — `status="failed"` already carries that, and a value that duplicates another attribute invites the two to disagree.
- *Leave it and document the ambiguity in `SUPPORT.md`* — a documented trap is still a trap, and this one is free to remove today.

---

## ADR-026 - The block classifier types pictures with a caption pre-pass and the tier's own model

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** Four decisions, taken together because each depends on the others.

1. **Mechanism.** A cheap caption and context pre-pass first, then a classification call to the tier's existing vision model for anything the pre-pass cannot settle. Qwen3-VL-4B on the GPU tier, Moondream 2 on the CPU tier.
2. **No new dependency and no new model.** Nothing enters the manifest or the installer.
3. **`unknown` is retained below a confidence floor**, and is never replaced by a guess.
4. **Type and description are not folded into one model call.**

**Why the pre-pass first.** Books usually say what their pictures are. A caption reading "Figure 12. Photograph of the north face" has already answered the question, and spending seconds of a vision model's time to recover an answer sitting in the text is waste that scales with the length of the book. The pre-pass settles or abstains and never guesses: a caption naming terms from two families, or none, sends the block on. A weak guess there would be worse than no answer, because it would be spent *instead of* the model call rather than alongside it.

Only the caption is read. Surrounding prose mentioning a chart three sentences away is not a statement about this block. That prose is still collected and passed to the model, which can weigh it against the image — useful as evidence, useless as a rule.

**Why no new model.** A small dedicated ONNX image classifier would be more accurate at this specific task and would run in milliseconds. It was rejected on installer size: ADR-020 already accepts roughly 470 MB of PyTorch as unavoidable and records that the installer is large enough to be a stated expectation in `SUPPORT.md` rather than a defect. Adding weights for a component that has a serviceable free alternative — a vision model the user has already pulled for the description generator — spends that budget before there is any measurement saying it needs spending. The reversal condition is a benchmark, not an argument.

**Why `unknown` is kept.** The type selects the description prompt. A wrong type produces confident prose about the wrong kind of thing: a chart prompt applied to a photograph describes axes that do not exist, which is a worse listening experience than the generic handling an honest `unknown` already receives. This is the decision most likely to be "improved" by a later session, because discarding low-certainty answers lowers every accuracy figure on the reference set while raising the product's quality. It is guarded by a test that says so.

**Why type and description stay separate calls.** Folding them looks like an obvious saving — one call instead of two, and the model is looking at the image either way. It inverts ARCHITECTURE 4.6. The type exists *to select the prompt*; a combined call has to be given a single generic prompt, which is precisely the arrangement 4.6 rejects as noticeably worse. The saving is real and it buys the thing the component was built to avoid.

**Certainty, and where it goes.** Every classification carries a certainty on 0.00 to 1.00, the same scale as the description fence's `confidence` attribute (ARCHITECTURE 4.8, ADR-025), because that is its destination — the fence's confidence will combine the description's own signal with this one, and two scales would have to be reconciled by whoever writes that code.

It is derived from named evidence rather than from a model's opinion of itself. A caption that says "photograph" is a fact about the book and scores 0.90. A model's self-reported certainty is not calibrated against anything, so it is clamped below what a caption earns before use. Every result also records which evidence it rested on and the term or answer that decided it, so a wrong type names its own cause instead of requiring the block to be found and re-examined.

**The acceptance bar**, measured on the committed core set only:

- Cross-family confusion at or below 5%. Cross-family means a photograph or illustration called a diagram or chart, or the reverse — the failure that selects a wholly wrong description approach.
- Within-family confusion (photograph against illustration, diagram against chart) recorded in a confusion matrix, uncapped for v1. Both members of a pair receive broadly similar description treatment, so the cost is real and much smaller.
- `unknown` at or below 25%. Above that the model call is not earning its cost and the pre-pass should be doing more.

**Rejected.**
- *A dedicated ONNX image classifier* — better at the task, and it adds weights to an installer whose size is already a documented expectation. Revisit with a benchmark.
- *One model call producing type and description together* — cheaper, and it inverts the dependency 4.6 is built on.
- *Taking the model's best guess below the floor* — raises measured accuracy, lowers delivered quality.
- *Reading the surrounding prose as decisively as the caption* — a chart mentioned nearby is not a claim about this block, and treating it as one would make the pre-pass confidently wrong on exactly the books that discuss their figures most.
- *Passing the pre-pass's conclusion to the model as a hint* — would bias the answer and make any future agreement between the two an echo rather than evidence.

**Consequences.** Classification costs one vision call per picture the caption does not settle, on the same model the description generator will use, so a book's conversion time roughly doubles per undescribed picture before descriptions are even generated. This is the price of decision 2 and is the first thing a benchmark should measure.

**The numbers above are unmeasured.** The committed core set does not exist yet — the books are being gathered — so nothing here has been measured against anything. The harness, the manifest format, and the bar are in place; the instrument is not. Until it lands, no claim about this component's accuracy is evidence.

**Would reverse this.** On the mechanism: a measured conversion showing the per-picture model call dominates conversion time, which would make the dedicated classifier's installer cost worth paying. On the acceptance bar: a measured conversion showing within-family confusion costs more than assumed — that a photograph described by an illustration prompt is materially worse to listen to — which would cap it rather than leave it uncapped. On the floor: the measured `unknown` rate against the core set, which is what that number should be set from and currently is not.

---

*Companion documents: `ARCHITECTURE.md` (what the system is), `RUNBOOK.md` (how to operate it), `SUPPORT.md` (what users are told), `DATA.md` (what is held).*
