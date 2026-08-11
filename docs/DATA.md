# DATA

**Project:** Asoy
**Document status:** Specification. Describes what will be held, where, and for how long. Binding on the implementation, not a report on a running system.

> This document is short, and the shortness is the product working. Asoy runs entirely on your machine, so there is very little to account for. But "we don't collect anything" is a claim, and a claim is only worth something if it is specific enough to check. This is the specific version.

---

## 1. The short version

Asoy holds your books, your converted output, and some technical records about conversion jobs — **all of them on your own computer, in folders you control.** None of it is transmitted anywhere. The project maintainer has no access to any of it and no ability to obtain it.

**Converting a book makes no network request at all.** Asoy makes two outbound requests in total and neither happens during a conversion: a version check, which sends the version number and nothing else, and a one-off download of the text-recognition models, which happens only when you run the setup command that fetches them.

---

## 2. What Asoy stores on your machine

| What | Where | Contains | Lifetime |
|---|---|---|---|
| Source books | Wherever you put them | Your books | Never moved, copied, or modified by Asoy |
| Working files | Per-job temporary directory | Page images and cropped regions during processing | Deleted when the job finishes or is cancelled |
| Output files | The output folder you choose | Converted text and generated descriptions | Permanent; yours to keep or delete |
| Job records | Application data directory | Which tier ran, timings, error flags, file paths | Until you clear them |
| Application logs | Application data directory | Technical events, errors, file paths | Rotated; older logs deleted automatically |
| Settings | Application data directory | Your preferences, output folder path | Until you clear them or uninstall |

Exact paths are shown in the application and listed in `ARCHITECTURE.md` §7.

**Job records and logs contain file paths and processing metadata. They do not contain book text and do not contain page images.** This matters because logs are the thing you would attach to a bug report, and you should be able to do that without exposing what you were reading.

---

## 3. What Asoy never stores

Stated explicitly, because absence is easy to assert and easy to check in an open-source project.

- No account. There is no sign-up, no login, no user identifier.
- No email address, name, or contact information.
- No analytics, usage statistics, or feature telemetry.
- No crash reports sent anywhere. Crash information stays in your local log.
- No list of books you have converted, beyond the local job records you can delete.
- No device fingerprint, machine identifier, or installation ID.
- No licence key, activation, or entitlement check. The software is free.

---

## 4. What leaves your machine

One thing.

**The version check.** Asoy asks the release endpoint whether a newer version exists. The request carries the current version string. It does not carry a machine identifier, an installation ID, a document name, a usage count, or anything else. As with any web request, the receiving server sees the connecting IP address, which is unavoidable at the network level and is not logged or retained for this purpose.

**You can turn it off.** Disabling the version check in settings disables nothing else. You will simply need to check for updates yourself.

That is the complete list. There is no second request, no background sync, no opt-out analytics, and no cloud fallback when local processing fails — when it fails, Asoy tells you, rather than sending your page somewhere else to try again.

---

## 5. Components Asoy depends on

Asoy uses two things installed separately by you. They are separate programs with their own behaviour, and it is worth being clear about the boundary.

**Ollama** runs the AI model that writes descriptions. It runs on your machine and Asoy communicates with it locally, over `127.0.0.1`, which is your computer talking to itself. **Your page images go to Ollama, and Ollama is on your machine.** Ollama does download models from the internet when you pull them, which is a transfer *to* you, not *from* you. Ollama's own behaviour is governed by its own policy, not this one.

**Calibre** converts Kindle and legacy ebook formats. Asoy calls it as a command-line program with your file as input. It runs locally.

Neither receives anything from Asoy other than the file or image being processed, and neither is asked to send anything outward.

---

## 6. Deleting everything

1. **Output files** — delete them from wherever you saved them. They are ordinary files.
2. **Job records, logs, and settings** — clear them from within Asoy, or delete the application data directory.
3. **Uninstall Asoy** through Windows. This removes the program.
4. **Ollama and its models** are separate. Uninstall Ollama independently if you want the model files gone; they are large.

Nothing survives elsewhere, because nothing was ever elsewhere. There is no account to close and no deletion request to submit, because there is no one holding a copy.

---

## 7. Verifying this yourself

Asoy is open source under Apache 2.0. These claims are checkable rather than merely asserted, and you are encouraged to check them.

- **Read the network code.** There are two outbound requests in the codebase: the version check, and the model download in the OCR module that only the setup command reaches. A test asserts no other module can open a URL. If you find a third destination, or anything on the conversion path, that is a serious bug and worth reporting.
- **Watch the traffic.** Run a conversion with a network monitor or firewall logging enabled. You should see nothing at all. The version check happens at startup rather than during a conversion, and the model download only when you ask for it.
- **Read the logs.** Open one after a conversion and confirm it contains no book text.
- **Check the dependency list.** `ARCHITECTURE.md` §8 lists every third-party component and what it is for.

An open-source privacy claim that nobody ever checks is only slightly better than a closed-source one.

---

## 8. Regulatory position

Because Asoy processes everything locally and transmits no personal data, the project maintainer neither collects nor processes personal information from users of the software. There is no data controller relationship to manage, no data-processing agreement to sign, and no breach-notification exposure — there is nothing held to breach.

**One exception, stated plainly.** If you open an issue, send an email, or post in a discussion, that message is held by whoever hosts it (currently GitHub) and can be read by the maintainer and by the public. Logs you attach, your account name, and anything you write are all visible. **Do not attach anything you would not want public**, and redact file paths if they contain your name or reveal something private. This is the only place any of your information exists outside your own machine, and you put it there deliberately.

This section describes the project's posture, not legal advice.

---

## 9. If this ever changes

Any change to what Asoy transmits would be a change to the project's central promise. It would require:

- A recorded decision in `DECISIONS.md` superseding ADR-002 and ADR-013, with reasoning.
- A prominent entry in `../CHANGELOG.md`, not a buried line.
- Explicit, off-by-default, per-user consent. Never on by default, and never bundled into an update.
- An update to this document in the same release.

If you ever find that Asoy transmits something not described here, that is a defect of the highest severity and should be reported as one.

---

*Companion documents: `ARCHITECTURE.md` §7 and §9 (technical detail), `DECISIONS.md` ADR-002 and ADR-013 (why), `SUPPORT.md` (what users are told).*
