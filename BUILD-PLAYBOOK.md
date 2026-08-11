# BUILD PLAYBOOK

**A method for building software as a solo developer with AI assistance.**

Derived from the Asoy build (a Windows desktop application converting books into text for audiobook narration, fully local, Apache 2.0). Written to be reused on the next project. Nothing here is Asoy-specific except the examples, which are kept because a principle without a case is hard to apply.

**This document is method, not product documentation.** It is not part of Asoy's Ship Set (section 1) and describes no part of the application. It lives at the repository root of the build that produced it because that is where the lessons are still fresh, and it is revised in the same commit as the work that teaches something — see the convention in `CLAUDE.md` section 6.

**Expected to move.** Once a second project exists, this file belongs in a shared repository that both projects point at, and the copy here becomes a pointer to it. That relocation is planned, not drift.

---

## 0. The two ideas

Everything below rests on two moves. If you take nothing else, take these.

### Write the finished documentation first

Before any code exists, write the operational documentation as though the product already shipped, in the present tense, as-built. Not a plan. Not a proposal. A description of a system that runs.

This sounds like theatre and is not. Writing "the format router inspects the input and decides the path" forces you to decide what the paths are. Writing "DRM-protected files are rejected at ingestion with a clear message" forces you to decide that rejection happens at ingestion rather than partway through. A planning document lets you write "we will need to handle DRM somehow." An as-built document does not.

The present tense is the forcing function. It has no room for deferral.

### Split decisions from implementation across two surfaces

**The chat surface** (Claude.ai) makes decisions. It researches alternatives, weighs trade-offs, writes them up with rejected options and reversal conditions, and produces handoffs.

**The code surface** (Claude Code) implements. It reads the repository, edits files, runs tests, commits, and reports.

The routing rule is one sentence: **if the answer depends on running something, it belongs to the code surface; if the answer depends on what you want, it belongs to the chat surface.**

**Correcting what this playbook used to say.** It claimed the chat surface cannot see your files, and rested the whole division of labour on that. That was true when written and is not true now. With a GitHub context source syncing the repository into project knowledge, the planning surface reads committed files directly — verified by searching it for current `DECISIONS.md`, router source, and tests, all of which came back current rather than remembered.

What is actually true is narrower and more useful:

- **The planning surface reads the default branch as synced.** Committed and pushed work is visible to it. Uncommitted work, unpushed commits, and anything on another branch are not — and it has no way to tell a stale sync from a current one.
- **The division of labour still holds, for a better reason.** Reading a test is not running it. The code surface executes commands, watches them fail, and sees the working tree as it actually is. That gap is what makes the split real, and no amount of file access closes it.

The practical consequence is that the honest question changed. It is no longer "can it see the file" but **"has this been run, and against what."** A surface that can read a test suite and cannot run it will describe passing tests with total confidence.

---

## 1. The Ship Set

Nine documents. Eight are written before the build and maintained during it. The ninth cannot exist until there is a build to describe, and is added the moment there is.

| Document | What it does | Who reads it |
|---|---|---|
| `STATE.md` | Snapshot of where the build stands, every claim verified by a command | Any session starting cold, including you after a break |
| `ARCHITECTURE.md` | Components, data flow, where data lives, failure surfaces, known limitations | You, future maintainers, AI sessions |
| `DECISIONS.md` | Every decision as an ADR with rejected alternatives and a reversal condition | Anyone about to re-litigate a settled question |
| `RUNBOOK.md` | Release, rollback, recurring obligations, triage | You, under pressure, at an inconvenient hour |
| `INCIDENTS.md` | Failure log plus a standing pre-mortem | You, when something breaks the second time |
| `SUPPORT.md` | Every stated limitation, with the reason | Users, via a link rather than a retyped answer |
| `DATA.md` | What is stored, where, what is transmitted, how to delete it | Users, and you when a privacy claim is questioned |
| `CHANGELOG.md` | What shipped when, including which models or dependencies | Users tracing a behaviour change |
| `CLAUDE.md` | Invariants, blast radius, ask-first list, conventions | Every AI coding session, automatically |

### The parts that carry the weight

**Reversal conditions.** Every ADR ends with what would reverse it. Without this, a decision log is something you argue with on every re-read. With it, the entry answers back: *access to a Mac for testing, not a volume of requests.* A decision becomes something you can commit to and stop carrying.

**A decision recorded only in a code comment has the force of a decision and none of the protection.** The ask-first list keys on *anything with an ADR*, so a choice living in a comment is invisible to it and a session can reverse it silently — in either direction, since nothing flags either the change or the original. Asoy excluded a label from a classifier's answer set in a comment in one module, a sentence in `ARCHITECTURE.md`, and a test. It read as self-explanatory and was never questioned until a change collided with it, at which point the reasoning had to be reconstructed from the comment rather than read.

The test is not how complicated the choice is. **If it would be re-litigated, or would constrain a future session, it belongs in the decision log** — a comment explains what the code does, and says nothing about what was rejected or what would reverse it. Those two are the whole value of the entry.

**A stated rule for amending an append-only log.** "Append only, never edit" is the right default and it is incomplete, because some ADRs define a specification rather than settling a question — an output format, a schema, a protocol. Those grow. When the fourth attribute has to be added, the rule as written offers only a new ADR that says "as ADR-025, plus one field", and after three of those the specification is spread across four entries and no single one is current.

Write the exception down before you need it, or every instance becomes a judgment call and the log's shape depends on who was asked:

> An ADR that defines a specification may be amended in place when the amendment is purely additive and no consumer depends on the spec yet. Mark the amendment with its date, leave the original text intact, and point to it from the section it changes. Anything that changes, narrows, or reverses a decision gets a new ADR instead, however small.

The reasoning behind the exception is what keeps it from widening. Append-only exists so that reasoning which turned out wrong is never erased. **An additive amendment erases nothing**, so it does not engage the rule at all. A change that narrows or reverses does erase, which is why the same paragraph refuses it however small it looks — and "however small" is the load-bearing clause, since a reversal that felt minor is exactly the one that gets edited in quietly.

**The ask-first list in `CLAUDE.md`.** Name the things a session must not change silently: the output format, model choices, the dependency manifest, prompts, anything with an ADR. This list is also your routing rule for which surface handles a task.

**The blast radius table.** Where a mistake costs most, in descending order, each with what to do about it. An AI session that knows the output writer hides silent truncation behaves differently from one that does not.

**Explaining why in `SUPPORT.md`.** A bare "not supported" invites argument. "This is a limitation of open-source OCR generally, and cloud services do better, and we do not use them because nothing leaves your machine" ends the conversation and reinforces the product's premise in the same breath.

**A standing pre-mortem in `INCIDENTS.md`.** An empty incident log is useless. Fill it with the failures most likely to arrive first, each paired with the guard that would catch it. It is forecasting, labelled as forecasting, and it means the first real incident is recognised rather than diagnosed from zero.

**`STATE.md`, once code exists.** The other eight describe the system as it will be. None of them answers "what actually runs today", and reconstructing that from nine documents and a commit log is the first ten minutes of every cold session. One file, under a hundred lines: version and commit, what works with the command that proves each claim, what is half-built and what specifically is missing, what has not started, the open gaps, and the single next move.

Two rules make it worth having. **Every claim is verified by a command run while writing it**, so it is a report rather than a recollection — anything unverifiable says so in the file, because a confident snapshot that is wrong is worse than one admitting a hole. And **it is regenerated in the same commit as the change**, by re-running the commands rather than editing the lines you think moved. A stale `STATE.md` is the most dangerous document in the set, because it is the one a session trusts without checking.

### One correction the Asoy build forced

Documents written as-built will assert that code and users exist. The moment they land in a live repository, that becomes a false claim an AI session will reason from. **Add an honest status line to each without gutting the present-tense prose:**

> **Document status:** Specification. Describes the system as it is intended to exist when shipped. No implementation exists yet.

The prose stays valuable as a specification. The status line stops it from lying.

That is the line Asoy actually shipped with, and it is the wrong shape. Read the next subsection before copying it.

### The correction to that correction

**A status line is not written once. It is the one line in the document guaranteed to go stale, because it is the only line about the present.** Asoy's said "no application code exists yet" through five commits that added application code. Nothing flagged it: every commit updated the sections it touched, exactly as the convention required, and the header was not a section anybody touched.

Four things follow.

**Say what exists, not what does not.** "No implementation exists yet" has one true moment and is wrong forever after. A line naming which components are built and which are not stays useful as the answer changes, and it is obviously stale when it is, because a reader can check it against the tree.

**Give the document a "last verified against code" date.** An undated claim about the present is unfalsifiable. A dated one invites the check.

**Write the claim in the past tense.** Present tense breaks on the next change; past tense ages. A row reading *in sync with `origin/main` at `2abb065`* is a claim about now and is false the moment either side moves. The same fact as *`origin/main` was at `2abb065` when this was verified* stays true forever, and a reader comparing it to the tree learns the file's age instead of finding a lie. The symptom that exposed it: three consecutive pushes, each needing a correcting commit to that one row. **A line that needs fixing on a schedule is a line written in the wrong tense.**

**Sweep for the claim, do not fix the file you noticed.** The same sentence gets copied into every document in the set, and into the playbook that recommended it. Grep the phrase across the repository and fix every instance in one commit, or the next session finds the copy you missed and reasons from it.

The general form: **a claim about project state is a claim with an expiry date, and it belongs where it will be re-read, not where it was convenient to write.** The as-built documents are worth the discipline. The status line is the price of writing them early.

---

## 2. Phase sequence

### Phase 0, decide before writing

Work through the load-bearing decisions with the chat surface, one question at a time, each with numbered options and a recommendation you can accept or override. For Asoy that was: deployment shape, local versus cloud inference, hardware tiers, output format, distribution, licensing.

Do not batch these. Each answer constrains the next, and a bundled questionnaire produces answers to questions that no longer apply.

**Verify anything changeable before recommending it.** Library versions, licence terms, model availability, platform support. These move faster than any model's training data. A recommendation resting on a stale fact is worse than no recommendation, because it looks researched.

### Phase 1, write the Ship Set

One document at a time, with a review pass between each. Later documents cross-reference earlier ones, so writing them all at once produces a set that disagrees with itself.

### Phase 2, repository

Create it, place the documents, write the licence and `.gitignore` before any code. Two placement rules that are mechanical rather than aesthetic:

- `CLAUDE.md` must be at the repository root. That is where the code surface reads it. Anywhere else it is an ordinary file that gets ignored.
- `CHANGELOG.md` at root by convention. The rest can live in `docs/`.

Settle identity before the first push. Author name, licence copyright holder, and a noreply commit address. Public repositories are effectively append-only, and this is the last cheap moment.

### Phase 3, scaffold

Package manager, language version pin, directory structure mirroring the architecture's components, linter, test runner. **No heavy dependencies yet.**

### Phase 4, dependencies in stages

Add them one at a time, checking after each. Batching five packages into one command gives you one error and no idea which caused it.

**Define a hard stop before you start.** For Asoy it was PyMuPDF, an AGPL package that would have relicensed the project and which enters through transitive dependencies rather than direct installs. The instruction was explicit: if it appears, abort, do not work around it, report the chain. Name your equivalent before the first install.

Expect this phase to invalidate parts of the specification. That is the phase working, not failing.

### Phase 5, components, riskiest foundation first

Build in order of what everything else depends on. For Asoy: hardware tier detection, then the environment check, then a thin end-to-end slice, then the rest.

**Prove the foundation on real hardware before building on it.** Asoy's window rendering was assumed for several commits before anyone opened it. When it was finally run, it worked, but the tier detection underneath it did not, and the failure was invisible to a passing test suite.

### Phase 6, iterate

Loosen the reins. See section 4.

---

## 3. The handoff protocol

The chat surface produces prompts you paste into the code surface. Early ones should be tight. Later ones should not. Both halves of that matter.

### Structure of a tight handoff

Used during setup, and for anything touching an invariant or a licensing boundary.

```
Working directory: <absolute path>

<numbered tasks, each with exact anchor text and replacement>

EMIT MANIFEST
ANCHOR: provenance of every anchor. Read from the synced default
  branch, or carried from an earlier snapshot and therefore
  UNVERIFIED, or known to sit on uncommitted work and therefore
  unreadable from here. On mismatch, abort and report. Never
  approximate.
CHECK: exact commands with expected values, run before and after.
CONSTRAINT: what the payload must not contain, and what the
  artifacts the instructions produce must not contain.

COMMIT
<message>
```

### Why the manifest exists

Anchors go stale. An anchor that no longer matches produces either a failed edit or, worse, an approximate one.

**Abort-on-mismatch is the load-bearing instruction.** During the Asoy build it caught arithmetic errors in expected counts more than once, and each time the code surface reported the mismatch rather than adjusting the code to satisfy a wrong expectation. That behaviour is what makes the checks worth writing. It is worth having whatever the anchor's provenance, because the failure it catches is a wrong expectation, not a wrong quotation.

**State provenance honestly, and UNVERIFIED is no longer the default.** Where an anchor comes from now has three answers rather than two:

- **Read from the synced default branch.** Verified. This covers most anchors in a project with a GitHub context source, and labelling them UNVERIFIED out of habit is its own kind of dishonesty — it trains the code surface to ignore the label.
- **Read from the branch, but the working tree may have moved.** Uncommitted or unpushed work is invisible to the planning surface, and it cannot detect that from its side. If you know work is in flight, say so; the code surface confirms against the tree.
- **Carried from an earlier snapshot in conversation.** UNVERIFIED, as before.

The division holds either way: the surface that can see the working tree does the seeing.

### When to stop writing tight handoffs

**As soon as the foundations are in the repository.** A handoff that names modules, function signatures, return types, and test cases is not delegation. It is building through a keyhole while the code surface types.

Compare:

> Implement the format router and parser per ARCHITECTURE 4.3 and 4.4, plus the minimum through assemble and export to convert a text-only EPUB to Markdown. Read CLAUDE.md and DECISIONS.md first. DRM rejection at ingestion is invariant 2 and non-negotiable. Do not implement the Calibre subprocess or invent the description delimiter; both are ask-first. Decide the implementation shape yourself. Report only what I need to decide.

Four sentences. The code surface decides the module structure, because it can see the module structure.

**Give outcomes and constraints, not designs.** The constraints come from the Ship Set, which the code surface has already read.

---

## 4. Calibrating how much to gate

This is where the Asoy build went wrong and had to be corrected, so it gets its own section.

### Strict, one step at a time

Right for repository setup, identity, licensing boundaries, and anything where a skipped step silently breaks a later one. Confirm each step before issuing the next.

### Loose, outcome-driven

Right for feature work. The code surface builds, tests, commits, and reports. You review.

**The failure mode of over-gating is invisible while it happens.** Each step looks careful. What it actually produces is one round trip per commit through a surface that cannot run the code, while the surface that can run it waits for instructions.

### The convention that makes loose delegation safe

Add this to `CLAUDE.md`:

> **End every report with a DECISIONS NEEDED section**, or state explicitly that it is empty. List anything that touches an invariant, falls under the ask-first list, contradicts a recorded ADR, or resolves an ambiguity the specification did not settle. One line each, naming the choice made or deferred. Everything else is implementation and does not need to leave the code surface.

Now the code surface sorts its own output. You read a full report only when you want to. Usually you read four or five lines, and often they are empty.

### The convention that keeps this document true

Loose delegation means most of what is learned about the method is learned inside the code surface, where you are not watching. Unless something makes it write that down, the lesson stays there. So add a second convention to `CLAUDE.md`, next to the first:

> **A generalisable methodology lesson revises this playbook in the same commit**, and the revision is named in the DECISIONS NEEDED block. The trigger is narrow: something learned about *how to build* that would apply to a different project. A decision about the product goes to `DECISIONS.md`, a defect and its fix to `INCIDENTS.md`, a user-facing limitation to `SUPPORT.md`. The test is whether the lesson survives a change of project.

Two halves carry the weight. **Same commit**, because a lesson reconstructed from memory weeks later is a worse lesson — the specifics that made it useful are the first thing to go. And **narrow**, because a playbook revised on every commit stops being readable in one sitting, which is the only property that makes it worth reusing.

### Word conventions as procedures, not as intentions

A convention is followed by someone in a hurry who has already decided what they are doing. Its wording is the last thing standing between that and a plausible shortcut, so it should describe **an action to perform**, not **a state to achieve**.

The difference is not stylistic. "Keep `STATE.md` up to date" and "update the file" both leave the reader to decide which lines are stale, and deciding is where the error enters — the lines that look current are exactly the ones nobody re-checks. "Re-run the commands it cites and replace the output" leaves nothing to decide.

The case that produced this. Asoy's `STATE.md` convention already said *regenerate by running the commands, not by editing the lines you think changed*. Regenerating the file for an unrelated reason, the code surface refreshed a table of per-file test counts and wrote one of them — 61 — from memory. The real figure was 59. Running the command caught it before the commit.

Nothing was shipped wrong, and that is the point rather than a mitigation. **The convention held; the agent following it did not.** A rule that depends on the reader not taking an obvious shortcut is a rule that works until someone is moving quickly, and everyone is eventually moving quickly. The fix is not more discipline, it is wording with no shortcut in it.

Two tests when writing one:

- **Can it be satisfied by judgement?** If a reader can comply by deciding something looks fine, they will, and the times that judgement is wrong are the times it mattered.
- **Does it say what to run, or what to end up with?** Prefer the first. A command has an output you can paste; a desired state has an impression you can form.

The same test applies to trigger lists. Asoy's `STATE.md` names three triggers and explicitly excludes the test count, because a trigger that fires on nearly every commit turns the list into "always" and destroys its signal. **Say what is excluded and why**, or the next reader adds it back as an obvious omission.

---

## 5. Principles that earned their place

**You can only ship what you can test.** Asoy excluded a larger model tier and two platforms on this ground alone. A tier that cannot run on available hardware cannot be reproduced against a bug report, judged for quality, or checked for regression. This is a scope decision, not a limitation, and writing it down stops it being re-argued.

**Ask the question you actually mean.** Asoy detected its GPU tier with `torch.cuda.is_available()`, which reports whether the installed torch build has CUDA support, not whether the machine has a capable GPU. Those diverged: a working card classified as CPU tier for every user, because the default wheel is CPU-only. The fix was querying the driver directly. When something reports the wrong answer, check whether it is answering a different question.

**Implementation reality outranks the specification, and the specification should say so.** Every document carries a line: if the code and this document disagree, the code is right and this document is a bug, and fixing it is part of the change rather than a follow-up.

**The build will invalidate parts of the plan. Let it.** Asoy's OCR layer was specified as two engines and collapsed to one when dependency resolution revealed a third already present that ran the same models with fewer costs. That discovery was worth more than the plan it replaced.

**A fix without a guard is not finished.** Every bug fix carries a regression test, and the test names what it catches.

**Plausible wrong output is the highest severity, above visible breakage.** A conversion that silently drops a chapter looks like success. The user acts on it and finds out expensively. Rank severity by consequence, not by how loudly the failure announces itself.

**Never modify a byte of the user's content.** Where ambiguity must be resolved, fence rather than escape. Escaping is a modification wearing a technical costume.

**Verify before recommending anything changeable.** Versions, licences, availability, platform support. Cite what was checked and when.

**Prefer the smallest reversible step.** Amending a single unpushed commit is not the same decision as rewriting six pushed ones, and treating them as the same either paralyses you or makes you reckless.

---

## 6. Failure modes observed, and their fixes

| What happened | Fix |
|---|---|
| Documents claimed a shipped product that did not exist | Honest status line on each, present-tense prose retained |
| Chat surface wrote implementation specs instead of delegating | Outcomes and constraints, not designs |
| Strict step gating continued past setup into feature work | Release it once foundations are in the repository |
| Every report pasted back in full for sorting | DECISIONS NEEDED section, sorted by the code surface |
| Expected counts in handoffs were wrong | Abort-on-mismatch; the code surface reports rather than adjusts |
| A dependency ceiling persisted after its cause was removed | Diagnose before assuming; a lockfile can hold a stale pin |
| Personal email in public package metadata | Settle identity before the first push |
| Tier detection asked a library, not the hardware | Ask the question you mean |
| A decision log entry referenced text that did not exist | Cross-references are checkable; check them |
| An access limit was asserted without checking the mechanism that actually applied | Test the access before describing it. "I cannot see your files" was written into the method and outlived the sync that made it false |
| A handoff instructed an edit that broke a convention the same surface had recorded two commits earlier | The handoff asks the routing question before it is issued — new entry, or amendment? The planning surface holds the conventions and is the one that can answer it; leaving it to be discovered at execution turns every instance into a round trip. Executing and flagging was right here because the edit was reversible and the original text was preserved. Abort instead when it is not |

---

## 7. Starting a new project

1. Phase 0 decisions with the chat surface, one at a time, each verified.
2. Ship Set, one document at a time.
3. Repository, documents, licence, identity, first push.
4. Scaffold with no heavy dependencies.
5. Dependencies in stages, with a named hard stop.
6. Components, riskiest foundation first, proven on real hardware.
7. Release the gating. Outcomes and constraints. Read the DECISIONS NEEDED block.

The first three phases feel slow and are the reason the rest can be fast. By the time the code surface is building features, it has already read the invariants, the blast radius, the conventions, and the reasoning behind every settled question. That is why its reports start catching your errors instead of producing plausible-looking output.

---

*Reusable. Adapt the examples, keep the structure.*
