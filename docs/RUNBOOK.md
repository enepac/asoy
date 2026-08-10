# RUNBOOK

**Project:** Asoy
**Document status:** Operational. This is the document you open under pressure. Not yet exercised: no release has been made.

> Written for one person at an inconvenient hour. Procedures are checklists, not prose. If a step here is wrong, fix it the same day you discover it — a runbook you have learned to distrust is worse than no runbook.
>
> **Asoy has no uptime.** It is a desktop application, so nothing here is about keeping a server alive. The equivalent failures are: shipping a broken release, letting the signing certificate expire, and breaking compatibility with a dependency users installed themselves.

---

## 0. If something is wrong right now

Three questions, in order.

1. **Did a release just go out?** If yes, go to §5 (Critical bug shipped). Rolling back is cheap; diagnosing under pressure is not.
2. **Are many users reporting the same thing at once, without a release?** Something external changed under you — an Ollama update, a model retag, a Windows update. Go to §6.
3. **Is it one user?** It is almost certainly environment, not code. Go to §7 (Diagnostics) and work the triage table in §8.

---

## 1. Access inventory

Everything needed to ship. If any line is out of date, this runbook is broken.

| What | Where it lives | Notes |
|---|---|---|
| Source repository | `github.com/enepac/asoy` | Public, Apache 2.0 |
| Release artifacts | GitHub Releases | Installers attached per tag |
| Code signing certificate | `[LOCATION]` | See §2 for expiry |
| Signing certificate password | `[PASSWORD MANAGER ENTRY]` | Never in the repo, never in CI logs |
| CI/CD | GitHub Actions | Workflow: `[WORKFLOW FILE]` |
| Update endpoint | `[URL]` | Serves the version manifest |
| Domain / DNS | `[REGISTRAR]` | See §2 for renewal |
| Local build environment | `[PATH]` | Windows, matches CI as closely as practical |

**If you are ever unable to sign a release, you cannot ship.** That is the single point of failure in this list. Losing the certificate or its password stops all releases until a new certificate is issued and validated, which takes days, not hours.

## 2. Recurring obligations

Expiry is the classic solo-maintainer outage: nothing breaks until a date passes, and then everything does. Put every row in a calendar with a reminder **30 days ahead**, not on the day.

| Item | Expires / due | Reminder set | Consequence of missing it |
|---|---|---|---|
| Code signing certificate | `[DATE]` | ☐ | Every new installer triggers SmartScreen warnings |
| Domain registration | `[DATE]` | ☐ | Update endpoint dies; users silently stop getting updates |
| Dependency license audit | Quarterly | ☐ | AGPL creep (see §9) |
| Dependency security audit | Monthly | ☐ | Known CVEs shipping to users |
| Model compatibility check | On each Ollama minor release | ☐ | Silent quality regression or hard failure |

## 3. Release procedure

Do these in order. Do not skip the verification steps because the change was small — small changes are how unsigned or unversioned builds ship.

1. **Confirm the branch is clean** and CI is green on the release commit.
2. **Update `../CHANGELOG.md`.** Version, date, what changed. Write it before building, so the build and the record cannot disagree.
3. **Bump the version** in the single place it is defined. If it is defined in more than one place, fix that before continuing.
4. **Build the installer** from a clean checkout, not your working tree.
5. **Sign the installer.** Verify the signature after signing — do not assume it succeeded.
6. **Smoke test on a clean machine or VM.** Not your dev machine, which has every dependency already installed. The test that matters is the first-run environment check (§8) on a system that has never seen Ollama.
7. **Run one real conversion end to end**, on both tiers if you can reach both. A book with at least one chart, one table, and one scanned page.
8. **Tag the release** and attach the signed installer to GitHub Releases.
9. **Publish the version manifest** to the update endpoint. This is the step that actually makes the release live for existing users. Until it is done, the release exists but nobody gets it.
10. **Verify the update path** by pointing a previous-version install at the endpoint and confirming it sees the new version.

**Do not publish the manifest first.** Users will be offered an installer that is not yet attached.

## 4. Rollback

Rollback for a desktop app is not instant — users who already updated have the bad version on their machines. Speed matters because it caps how many more get it.

1. **Unpublish the version manifest entry**, or revert it to the previous version. This stops new users from being offered the bad build. Do this first, before diagnosing anything.
2. **Mark the GitHub release as a pre-release** so it drops out of "latest."
3. **Do not delete the release.** Users who need to report against it need it to exist. Deleting artifacts makes the incident undiagnosable.
4. **Publish a short note** in the release description saying what is wrong and what users should do.
5. **If the bad version corrupts or destroys user data**, this is a different severity. Notify prominently — README, release page, wherever users look — and give explicit recovery steps before working on the fix.

Users on the bad version will not automatically downgrade. Assume they stay there until they act, and write instructions accordingly.

## 5. Emergency: critical bug shipped

Order matters here; the instinct to fix first is wrong.

1. **Stop the bleeding.** Rollback per §4. Do this before you understand the bug.
2. **Reproduce it.** No fix is designed against an unreproduced bug. Get the exact input, tier, version, and OS build.
3. **Assess the blast radius.** Does it produce wrong output, no output, or destroyed input? Wrong output that looks plausible is the most dangerous case, because users act on it — a book converted with silently truncated chapters can reach a finished audiobook before anyone notices.
4. **Fix the cause, not the symptom.** If you ship a symptom patch under time pressure, say so in the commit and open an issue for the real fix immediately.
5. **Add a regression guard** — a test that fails if this returns. A fix without a guard is not done.
6. **Release per §3.** Do not shortcut the smoke test because the fix is urgent. Urgent fixes are exactly where second bad releases come from.
7. **Write it up in `INCIDENTS.md`.** Date, symptom, cause, fix, prevention. Four lines. Do it the same day.

## 6. Emergency: something external broke

Asoy depends on things it does not control: Ollama, model tags, PDF-rendering behaviour, Windows itself. A sudden cluster of identical reports with no release on your side means one of them moved.

1. **Identify what changed.** Check Ollama's release notes, the model's tag history, and recent Windows updates against the date the reports started.
2. **Reproduce with the new version** of the external thing.
3. **Decide: pin or adapt.** Pinning the model tag or the Ollama version range is the fast mitigation. Adapting is the real fix.
4. **Communicate.** Users cannot tell your bug from someone else's. A note on the repo saying "Ollama 0.X changed Y, here is the workaround" prevents a flood of duplicate reports.
5. **Record it in `INCIDENTS.md`** and, if a version range needs pinning permanently, in `DECISIONS.md`.

## 7. Diagnostics: what to ask a user

Standard opening set. Ask for all of it at once; a five-round back-and-forth wastes both parties' time.

- Asoy version.
- Hardware tier shown in the UI (GPU or CPU).
- GPU model and VRAM, if applicable: `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv`
- Ollama version, and whether it is running.
- Which model is pulled: `ollama list`
- Windows version and build.
- Source file format, and roughly how large.
- Whether the file has DRM.
- The job record and application log (paths in `ARCHITECTURE.md` §7).

**Logs contain no book text and no page images** — file paths and block metadata only. You can say this plainly when asking, and it removes the main reason people hesitate to send them.

**Do not ask for the book.** Copyright aside, you rarely need it. If you genuinely do, ask whether they can reproduce with a public-domain file instead.

## 8. Failure triage

| Symptom | Most likely cause | Fix |
|---|---|---|
| App reports Ollama not found at startup | Ollama not installed | Point to installer; the first-run check should already do this |
| App reports Ollama unreachable | Ollama installed but not running, or on a non-default port | Start Ollama; check the port |
| App reports model not pulled | Model never downloaded | `ollama pull [MODEL]`; verify with `ollama list` |
| Job starts, then falls back to CPU tier | VRAM exhausted, or another process is holding the GPU | Check `nvidia-smi` for competing processes; expected on cards under 6 GB |
| Conversion very slow | CPU tier on a long book | Expected. Confirm tier; set expectations rather than debugging |
| Output has garbled or missing text | Scanned source, OCR below confidence | Check for flagged pages in the review UI; PDF source is the usual culprit |
| Chapters out of order | Reading-order error in a complex layout | Parser limitation, not a bug in Asoy. Confirm source is PDF; suggest EPUB if available |
| Descriptions vague or wrong on charts | Expected on CPU tier, possible on GPU tier | Documented limitation. Confirm tier before treating as a defect |
| File rejected at ingestion | DRM, or corrupt file | Check the rejection message; DRM is a boundary, not a bug |
| MOBI/AZW3 fails to convert | Calibre missing or subprocess failed | Check Calibre is installed and on PATH; read the captured stderr |
| Job resumes at the wrong place | Checkpoint state invalid after source file changed | Clear job state and restart the conversion |
| Empty output file | Job failed silently — this should not happen | Escalate. Silent failure is a defect regardless of cause |

Anything not in this table and reproducible goes to `INCIDENTS.md` after resolution, and its symptom row gets added here.

## 9. Dependency updates

**Monthly, security.** Check advisories for Docling, PaddleOCR, Tesseract, pypdfium2, and the packaging toolchain. Anything with a known exploit path gets an out-of-cycle release.

**Quarterly, licensing.** Re-run the license scan across the full transitive tree. You are looking for one thing above all: **has anything pulled in PyMuPDF or another AGPL package?** This is prohibited per `DECISIONS.md` ADR-011, and it enters through transitive dependencies, not direct ones. This check belongs in CI; until it is there, do it by hand and treat that as debt.

**On each Ollama minor release.** Verify both tier models still load and produce output of comparable quality. Model tags get retagged upstream, and a silent quality regression is far worse than a hard failure because nobody reports it.

**Model updates specifically.** Never change the model a shipped version depends on without testing description quality on a fixed reference set — the same book, the same charts, compared side by side. Without a reference set this check is a vibe, and description quality is the product.

## 10. What is not an incident

Do not open an incident, and do not treat as a defect:

- A user on hardware below the GPU tier getting reduced quality. That is documented behaviour.
- DRM-protected files being rejected. That is a stated boundary (`DECISIONS.md` ADR-014).
- Handwriting not being recognised. Known limitation of open-source OCR.
- A PDF with a complex layout producing imperfect reading order. Known limitation.
- Requests for macOS builds. Answered in `DECISIONS.md` ADR-007.
- A chart description that is qualitatively right but numerically vague on the CPU tier. Expected.

Each of these has a written answer in `SUPPORT.md`. Point to it rather than re-explaining, and if the written answer is unclear enough that people keep asking, that is a documentation fix, not a code fix.

---

*Companion documents: `ARCHITECTURE.md` (what the system is), `DECISIONS.md` (why it is shaped this way), `INCIDENTS.md` (what has broken before), `SUPPORT.md` (what users are told).*
