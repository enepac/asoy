# INCIDENTS

**Project:** Asoy
**Document status:** Living log. Append-only.

> Production teaches things planning cannot. This file is where those lessons stop being anecdotes and start being data.
>
> **Why this is worth the effort.** A solo maintainer re-encounters the same class of failure repeatedly, and without a written record each recurrence feels like the first time. Four lines written the day something breaks are worth more than an hour of reconstruction three months later.

---

## How to write an entry

Write it **the same day**, before the relief of having fixed it erases the details. Four fields, plus one that matters more than the rest.

```
### INC-NNN — [one-line symptom as the user experienced it]

**Date:** YYYY-MM-DD · **Severity:** [S1-S4] · **Version:** [affected] · **Fixed in:** [version]

**Symptom.** What the user saw. Their words where possible, not your diagnosis.
**Cause.** The actual root cause, not the first plausible explanation.
**Fix.** What changed, and where.
**Prevention.** The guard that makes this class of failure visible or impossible next time.
```

**The Prevention field is the point of the document.** An entry without one records that something broke and nothing changed, which is how the same bug returns. If the honest answer is "none yet," write that — an admitted gap is trackable, a fabricated guard is not.

Write the Symptom in the user's terms. Six months on, you will search this file by what went wrong from outside, not by what you eventually discovered inside.

## Severity

| Level | Definition | Response |
|---|---|---|
| **S1** | Destroys or corrupts user data, or produces plausible-looking wrong output users could act on | Rollback immediately (`RUNBOOK.md` §4), notify prominently, fix before anything else |
| **S2** | Application unusable for a substantial share of users | Rollback, fix, out-of-cycle release |
| **S3** | A feature broken or degraded; workaround exists | Fix in the next scheduled release |
| **S4** | Cosmetic, or affects a narrow edge case | Fix when convenient |

**Plausible wrong output is S1, not S3.** A conversion that silently drops a chapter or fabricates a description looks like success. The user takes it downstream, narrates it, publishes it, and discovers the problem when it is expensive. Failures that announce themselves are less dangerous than failures that don't.

## Standing pre-mortem

Not incidents. These are the failures most likely to arrive first, written down so that when one happens it is recognised rather than diagnosed from scratch. Delete a row when its guard is in place and proven; move it to the log if it happens first.

| Likely failure | Why it is likely | Guard that would catch it |
|---|---|---|
| Signing certificate expires unnoticed | Nothing breaks until a date passes; no alert fires | Calendar reminder 30 days out (`RUNBOOK.md` §2) |
| Ollama minor release changes behaviour | External dependency outside your control, updated by users independently | Compatibility check on each Ollama release |
| Model tag retagged upstream, quality shifts silently | Tags are mutable; a quality regression produces no error | Fixed reference set, compared side by side before accepting a model change |
| Transitive dependency pulls in an AGPL package | PyMuPDF is the most convenient PDF library in Python and enters through dependencies, not direct installs | License scan in CI (`DECISIONS.md` ADR-011) |
| Long job on the CPU tier fails near the end | Multi-hour jobs have many chances to be interrupted | Chapter checkpointing (ADR-015), plus a test that kills a job mid-book |
| Chapter silently dropped from output | Assembler failure that produces a plausible file | Chapter-count assertion between parse and emit |
| Version manifest published before installer attached | Ordering mistake under release pressure | Release checklist step order (`RUNBOOK.md` §3) |
| Disk fills mid-job, truncated output written | Page images for a large book are substantial | Pre-write space check (`ARCHITECTURE.md` §10) |

The most dangerous rows here are the silent ones — retagged models, dropped chapters. They produce no error, no report, and no signal that anything is wrong. Assertions catch these; user reports do not.

## Pattern review

Every fifth entry, or quarterly, read the whole log and ask one question: **is the same root cause appearing more than once?**

Three occurrences of the same class is not bad luck. It means the fix has been at the symptom level each time, and the structural cause is untouched. When that happens, stop patching and change something architectural — an assertion, a test, a design constraint, a boundary. Record the structural change in `DECISIONS.md`, not here.

If a class recurs *after* a structural fix, that fix failed. Do not add a second patch on top of it — reopen and replace it, and note in the entry that a prior fix did not hold. A fix that needs propping up is the wrong fix.

Track here as patterns emerge:

| Pattern | Occurrences | Structural fix | Held? |
|---|---|---|---|
| *(none yet)* | | | |

## What does not belong here

These are documented behaviour, not incidents. They have written answers in `SUPPORT.md`.

- Reduced description quality on the CPU tier.
- DRM-protected files rejected.
- Handwriting not recognised.
- Imperfect reading order from complex PDFs.
- Requests for macOS builds.

Logging documented limitations as incidents inflates the record and buries the entries that matter. If users keep reporting one of these, the fix is clearer documentation, and that belongs in `SUPPORT.md`.

---

## Log

Newest entries at the top.

All three below were found in one triage session, on one route, stacked so that each hid the next. None had shipped to a user, because no release exists — but all three were live in the working tree, and a user converting a scanned PDF on that build would have hit every one.

---

### INC-003 — Scanned PDFs failed with a compiler error, and OCR ran on the wrong engine

**Date:** 2026-08-10 · **Severity:** S2 · **Version:** unreleased · **Fixed in:** unreleased

**Symptom.** Converting a scanned PDF failed with `InductorError: InvalidCxxCompiler: Compiler: cl is not found`. Nothing in the message mentioned OCR, PDFs, or anything a user could act on.

**Cause.** Two faults in one route. `onnxruntime` was never in the dependency tree, so RapidOCR silently fell back to its PyTorch engine — a different engine from the one ADR-019 records, announced only in a log line. That engine, and Docling's own layout model, invoke `torch.compile`; TorchInductor shells out to a C++ compiler, and `cl.exe` is absent on any Windows machine without Visual Studio, which is essentially all of them.

**Fix.** `onnxruntime` added to the manifest so the documented engine is the one that runs, and `torch.compile` disabled in-process (ADR-029, decisions 2 and 3).

**Prevention.** A test asserts `onnxruntime` is importable and that every model path Asoy passes is an `.onnx` file, since the engine is chosen by what it is handed. A second asserts `torch.compile` is disabled. Both are cheap; neither would have fired without the end-to-end test in INC-001, which is what made the route visible at all.

---

### INC-002 — Converting a book silently downloaded 30 MB from a third-party host

**Date:** 2026-08-10 · **Severity:** S2 · **Version:** unreleased · **Fixed in:** unreleased

**Symptom.** Starting a conversion of a scanned PDF produced several seconds of unexplained delay. The log, read for a different reason, showed four downloads from `modelscope.cn` totalling about 30 MB.

**Cause.** RapidOCR fetches its model weights on first use. Nothing in Asoy asked for this and nothing disclosed it. `ARCHITECTURE.md` §9 stated "exactly one outbound request exists", and `DATA.md` told users to watch their traffic and expect to see only the version check. Both were false the first time anyone converted a scanned page. No user content was transmitted, so invariant 1's substance held — but a network request triggered by "convert this book" is the worst available shape for one, and the weights were being written into `site-packages`, which is read-only in a packaged install.

**Fix.** Weights became a checked prerequisite fetched by an explicit user command, stored in a directory Asoy controls, with every model path passed to Docling so there is nothing left to resolve (ADR-029, decision 1). Documentation corrected across six files.

**Prevention.** A test asserts that the only module in the package containing a URL opener is the OCR module, and that neither the parser nor the orchestrator can reach the downloader. The claim that a conversion transmits nothing is now enforced rather than asserted.

---

### INC-001 — Every OCR path was dead, and four books converted anyway

**Date:** 2026-08-10 · **Severity:** S2 · **Version:** unreleased · **Fixed in:** unreleased

**Symptom.** Converting a PDF failed immediately with `AttributeError: module 'cv2' has no attribute 'setNumThreads'`.

**Cause.** `opencv-python` had unpacked without its `__init__.py` and without its extension module, leaving a `cv2/` directory containing only a DLL and two subdirectories. `import cv2` therefore succeeded and produced an empty namespace package, so every call into it failed. A reinstall fixed it; the installed version never changed.

**The first diagnosis was wrong and is worth recording.** It blamed a version incompatibility — opencv-python 5.0.0.93 against RapidOCR's `>=4.5.1.48` — and proposed pinning below 5. The pin was never applied: `uv pip install "opencv-python<5"` reinstalled the same version, and it was the reinstall that fixed it. A version bound would have appeared to work, for the wrong reason, and would have constrained the manifest for no benefit.

**Fix.** None in the manifest. The install was repaired, and the defect is now detectable.

**Prevention.** A test asserts `cv2.__file__` is not None and `setNumThreads` is callable, because a bare import passes on the broken install and is not a test of anything. More importantly, an end-to-end conversion of a generated image-only PDF now runs in the default suite. **304 tests passed while this route was completely dead**, because every one of them converted a declarative format and EPUB never touches OCR. A route with no end-to-end test accumulates defects silently, and they surface together.

---
