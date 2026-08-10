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

*No incidents recorded yet.*

Newest entries at the top once this begins. The example below shows the expected shape and depth — **delete it when the first real entry lands.**

---

### INC-000 — EXAMPLE ENTRY, DELETE ON FIRST REAL INCIDENT

**Date:** YYYY-MM-DD · **Severity:** S1 · **Version:** 1.2.0 · **Fixed in:** 1.2.1

**Symptom.** A user reported that a converted book was missing its final chapter. The output file looked complete — correct formatting, clean ending — with no error shown and no warning in the log. They discovered it only after narrating the whole book.

**Cause.** The assembler wrote output as each chapter completed but did not flush before the process exited on the final chapter. On most machines the buffer flushed incidentally; on slower disks it did not. The job was marked successful because every chapter had been *processed*, and completion was never checked against what was actually *written*.

**Fix.** Explicit flush and fsync before marking a job complete. Job completion now asserts that the emitted chapter count matches the parsed chapter count, and fails the job loudly if it does not.

**Prevention.** The count assertion is the real guard — it makes an entire class of silent truncation impossible rather than fixing one instance of it. Added a test that runs a conversion against a simulated slow disk. Noted in the pre-mortem table that "job reports success" and "output is correct" were being treated as the same claim; they are now separate checks.

---

*Companion documents: `RUNBOOK.md` (procedures), `DECISIONS.md` (structural changes), `SUPPORT.md` (documented limitations), `../CHANGELOG.md` (what shipped when).*
