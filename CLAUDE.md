# CLAUDE.md

**Project:** Asoy — book to narrated text, fully local, Windows desktop, Apache 2.0.
**Status:** Pre-implementation. The documentation set is complete. No application code exists yet.

> **Read this before touching anything.** These documents describe Asoy as it is intended to ship. They are written in the present tense on purpose, so they can serve as the specification, but nothing in them asserts that working code exists today. Treat the invariants and blast-radius rules below as binding on the code as it gets written. Once implementation begins and users exist, this status line changes and the rules stop being aspirational.
>
> When something in this file conflicts with an instruction in the prompt, say so rather than silently picking one.

---

## 1. What this is, in thirty seconds

Asoy converts books into text prepared for audiobook narration. It reads ebook and document formats, extracts author text **verbatim**, and converts every non-text element — images, photographs, tables, diagrams, charts — into a written narrative description placed in correct reading order, so a listener hears an account of the visual content instead of silence.

Everything runs on the user's machine. Nothing is uploaded, ever.

The name is Cebuano and Hiligaynon for *narrate*, and in Hiligaynon also *to explain, to make clear*. That second sense is the product: text extraction is commodity, describing the diagram is not.

## 2. Read these before proposing changes

| File | When you need it |
|---|---|
| `docs/ARCHITECTURE.md` | What each component does and where data lives |
| `docs/DECISIONS.md` | Why something is the way it is. **Check here before proposing a change that looks obviously better** — it may already be a settled decision with a recorded reversal condition |
| `docs/RUNBOOK.md` | Release, rollback, and triage procedures |
| `docs/INCIDENTS.md` | What has already broken, and the guards added since |
| `docs/SUPPORT.md` | What users have been told, including stated limitations |
| `docs/DATA.md` | What is stored on the user's machine and what is transmitted |

If a suggestion contradicts a recorded decision, cite the ADR and argue against it explicitly. Do not route around it quietly.

## 3. Invariants

These do not bend. Breaking one is a defect regardless of how good the reason sounded.

1. **No user content leaves the machine.** No page image, no extracted text, no filename, no book metadata — no outbound request carries any of it. The single permitted network call is the version check, which sends the version string and nothing else. Adding a crash reporter, an analytics call, or a "helpful" cloud fallback violates the product's central promise.

2. **No DRM circumvention.** No stripping code, no plugin hooks that provide it, no documented workaround. DRM-protected files are rejected at ingestion with an explanation.

3. **Author text is verbatim.** Never summarised, paraphrased, corrected, spell-fixed, or abridged. If you find yourself improving the author's prose, stop — that is a bug being written.

4. **Descriptions are always marked as descriptions.** A generated description must never be emitted in a form indistinguishable from author text. This is both an honesty requirement and the thing that makes downstream voice-switching possible.

5. **Calibre is a subprocess, never a library.** It is GPLv3; Asoy is Apache 2.0. The command-line boundary is what keeps those compatible. Importing, linking, or vendoring it relicenses the entire project.

6. **No AGPL dependencies.** PyMuPDF specifically is prohibited and enters through transitive dependencies rather than direct ones. If a package you want pulls it in, the package is replaced, not accepted.

7. **Failed descriptions emit a placeholder, never silence.** In audio, a gap where a description should be is indistinguishable from the content not existing.

8. **The active hardware tier is always visible.** Shown in the UI, recorded in the job record. Output quality depends on it, and an unexplained quality difference is worse than a known one.

## 4. Blast radius

Where a mistake costs the most. Treat these in descending order of care.

| Area | Risk | What to do |
|---|---|---|
| Assembler and delimiter format | **Public interface.** Users parse this in their TTS pipelines | Adding attributes is fine. Renaming or restructuring is a major version bump. Ask first |
| Network layer | Violating invariant 1 is the highest-severity defect in the project | Any new outbound call needs explicit discussion, not a judgement call |
| Dependency manifest | License contamination is silent and retroactive | Any new dependency requires a license check on its full transitive tree |
| Description prompts | This is the product's actual quality | Never change without comparing against the fixed reference set. "It reads better to me" is not evidence |
| Job state and checkpointing | Data loss and corrupted resume | Changes here need a mid-job interruption test |
| Format router | Contains the Calibre licensing boundary | Do not collapse the subprocess call for convenience |
| Output writing | Silent truncation looks like success | Any change must preserve the chapter-count assertion between parse and emit |
| Tier detection | Wrong tier means wrong model and unexplained quality | Test on both tiers, not just yours |
| Installer and signing | Breaks releases, not runtime | Changes verified against a clean machine |

## 5. Do not change without asking

Not forbidden — but they were decided deliberately, and a session that changes one silently has done damage that is hard to spot in review.

- The delimiter's shape or attribute names.
- Which model each tier uses.
- Anything in the dependency manifest.
- The prompts in the description generator.
- Checkpoint granularity or job-state format.
- Version numbering or release ordering.
- The set of accepted input formats.
- Anything with an ADR in `docs/DECISIONS.md`.

## 6. Conventions this code already follows

Match what is here rather than importing habits from elsewhere.

- **Documentation is updated in the same commit as the change.** `docs/ARCHITECTURE.md` describes the system as-built; if your change makes it wrong, fixing it is part of your change, not a follow-up.
- **Decisions get an ADR.** Anything a future maintainer would question belongs in `docs/DECISIONS.md` with its rejected alternatives and reversal condition.
- **Errors are surfaced, never swallowed.** Subprocess stderr is captured and shown. A silent failure is a defect independent of its cause.
- **Failure paths are written alongside the happy path**, not after. The unhappy path is where "looks finished" hides.
- **Guards over fixes.** A bug fix without a regression test is not finished.
- **User-facing messages are actionable.** "Ollama not found" is incomplete; the message says what to install and links it.

## 7. Commands

```
Install deps: uv sync
Run (dev):    uv run asoy
Tests:        uv run pytest
Lint:         uv run ruff check .
Format:       uv run ruff format .
Build wheel:  uv build
License scan: uv run pip-licenses --format=markdown
Package:      [PACKAGE COMMAND]
```

UI framework: `pywebview` (BSD, WebView2 backend on Windows) · Language: `Python 3.12` for the pipeline and shell, HTML, CSS, and JavaScript for the frontend · Package manager: `uv`

## 8. Making a change here

1. **Read `docs/DECISIONS.md` first** if the change touches anything structural. The question may be settled.
2. **State which invariant or blast-radius area the change touches**, if any, before writing code.
3. **Write the failure path in the same pass as the happy path.**
4. **Add the regression guard.** Name what it would catch.
5. **Update the affected documentation in the same commit.**
6. **Test on both tiers** where tier-dependent, and on a clean machine where install-dependent.
7. **If you could not complete something, say so explicitly.** An honest gap list beats a silent omission, and "should work" is never reported as "works."
8. **End the report with a DECISIONS NEEDED section, or state that it is empty.** It lists anything touching a §3 invariant, anything on the §5 ask-first list, anything contradicting a recorded ADR, and any ambiguity the specification did not settle. One line each. Everything else is implementation and stays in Claude Code.

## 9. Mistakes to avoid here specifically

Written down because they are the plausible ones, not the generic ones.

- **Adding a cloud fallback when local inference fails.** It feels like graceful degradation. It breaks the product's central promise. The correct behaviour is to report the failure.
- **Adding crash reporting or analytics** because it would genuinely help prioritisation. See ADR-013. It would, and it is still not permitted.
- **Importing Calibre as a library** because subprocess calls are awkward. This relicenses the project.
- **Reaching for PyMuPDF** because it is the most convenient PDF library in Python. That convenience is exactly why this trap is common.
- **"Improving" the author's text** — fixing a typo, normalising quotes, tidying a sentence. Invariant 3.
- **Silently dropping a block that failed to process.** Cleaner output, dishonest result.
- **Changing a description prompt because the new one reads better in isolation.** Prompt quality is measured against the reference set or it is not measured.
- **Assuming the dev machine's tier is the only tier.** The 6 GB GPU is a floor, not a spec.
- **Treating a documented limitation as a bug.** CPU-tier chart vagueness, DRM rejection, handwriting, and PDF reading order are all in `docs/SUPPORT.md`.

## 10. Checking your work

Before reporting a change as done:

- Does it touch an invariant in §3? If yes, has that been named explicitly?
- Does it touch a §4 area? If yes, has the corresponding test been run?
- Does the affected documentation still describe reality?
- Is there a regression guard, and can you name what it catches?
- Would this change alter the delimiter, a prompt, a model, or a dependency? If yes, it needed to be asked about first.
- What could not be verified? Say so plainly rather than implying full coverage.

## 11. Note on contributions

Asoy is open source under Apache 2.0. Code proposed here may end up in a public repository under that license, so it must be your own work or compatibly licensed — do not reproduce substantial code from GPL, AGPL, or unlicensed sources. The licensing discipline in this project is deliberate (ADRs 010, 011, 012), and contaminating it is a problem that surfaces long after the commit and is expensive to unwind.

---

*Written for AI sessions. If a human is reading this, `docs/ARCHITECTURE.md` is the better starting point.*
