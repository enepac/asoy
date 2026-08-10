# SUPPORT

**Project:** Asoy
**Audience:** Users. Written to be linked, not explained. Not yet published: there are no users at this stage.

> **For the maintainer.** Every recurring question gets its answer written here once. When someone asks, link the section rather than retyping it. If people keep asking about something that is already documented, the documentation is unclear — fix the wording here rather than answering again.
>
> Each limitation below explains *why*, not just *what*. A bare "not supported" invites argument; an explanation ends the conversation.

---

## Before reporting a problem

Most reports resolve here.

1. **Is Ollama installed and running?** Asoy needs it. See [Setup](#setup-ollama).
2. **Is the required model pulled?** Run `ollama list` and check it appears.
3. **Which tier are you on?** Asoy shows this in the interface. Quality expectations differ, and several things that look like bugs are the CPU tier working correctly.
4. **Is your source file a PDF?** PDFs produce worse results than EPUBs, for reasons explained below.
5. **Is the file DRM-protected?** Asoy cannot open those, by design.
6. **Is it listed under [Known limitations](#known-limitations)?** Several common surprises are documented behaviour.

If none of these apply, see [Reporting a problem](#reporting-a-problem).

---

## Setup: Ollama

Asoy does not include the AI model that writes descriptions. It uses **Ollama**, which you install separately.

This is the most common thing people get stuck on, so here is the whole path:

1. Install Ollama from its official site.
2. Make sure it is running. On Windows it runs in the background after installation.
3. Pull the model Asoy asks for. Asoy tells you the exact command on first run.
4. Start Asoy. It checks all three of the above and tells you specifically which one is missing.

**Why isn't it bundled?** Ollama already solves model downloads, GPU detection, and updates well. Bundling all of that would make Asoy's installer several gigabytes and would mean re-releasing Asoy every time a model updates. Separating them keeps Asoy small and lets you update the model without waiting for us.

If Asoy says Ollama is unreachable but Ollama is running, it is usually on a non-default port. Check Ollama's settings.

---

## Hardware tiers and what to expect

Asoy runs in one of two modes, chosen automatically based on your hardware. The active tier is always shown in the interface.

**GPU tier** — you have a graphics card with 6 GB of video memory or more. Descriptions are fuller and more accurate.

**CPU tier** — you do not. Asoy still works, using a smaller model.

**The difference is real, and it shows up most in charts.** On the CPU tier, a chart is usually described by its shape and direction — that a line rises steeply through the middle of the period, that one bar is far taller than the others — rather than by its specific values. Photographs, illustrations, and simple diagrams degrade much less.

If a chart description seems vague, check your tier before reporting it. On the CPU tier, that is the model working as expected rather than a fault.

**Conversion on the CPU tier is slow.** A full-length book can take hours. This is not a bug, and the job resumes from the last completed chapter if it is interrupted.

---

## Known limitations

These are permanent or long-standing, and each has a reason.

### DRM-protected books cannot be converted

Asoy rejects them at the start rather than failing partway through.

**Why.** DRM removal is a legal question, not a technical one, and a tool that circumvents it could not be distributed or contributed to. Asoy works only with files you can already open in a normal reader. This will not change.

### Handwriting is not reliably read

Handwritten notes, annotations, and manuscripts produce poor results or none.

**Why.** This is a limitation of open-source text recognition generally, not of Asoy specifically. The available engines are strong on printed text and weak on handwriting. Commercial cloud services do better, and Asoy does not use them because nothing on your machine is sent anywhere.

### PDFs produce worse results than EPUBs

If you have a choice of format, choose EPUB. If your PDF has multiple columns, sidebars, pull quotes, or margin notes, expect reading-order mistakes.

**Why.** An EPUB describes its own structure — this is a chapter, this is a heading, this paragraph follows that one. A PDF describes where ink goes on a page and leaves the structure to be inferred. Most of the time that inference is right. On complex layouts it is not, and no later step can repair it.

### Chart descriptions are approximate

Even on the GPU tier, a dense chart with several series is described more reliably by its shape than by its exact values.

**Why.** Reading precise numbers off a chart image is one of the hardest things for a vision model to do, and Asoy uses models that fit on your machine rather than the largest ones available. This is the direct cost of everything staying local.

Descriptions Asoy is unsure about are flagged for review, so you can correct them before narration.

### The installer is large

Expect a download in the region of a gigabyte, and more on disk after installation.

**Why.** Asoy's document parser uses machine-learning models for page layout, reading order, and table structure, and those models run on PyTorch. There is no configuration in which the parser works without it. This is the single largest component of the install, and it is not the AI model that writes descriptions, which Ollama manages separately and downloads on its own.

### Windows only

There are no macOS or Linux builds.

**Why.** Asoy is maintained by one person. Shipping a platform means being able to test on it and reproduce problems reported on it. Releasing builds that cannot be supported would be worse than not releasing them.

### Some visual elements cannot be described

Occasionally the model fails on a block. When that happens Asoy writes an explicit placeholder rather than leaving a gap.

**Why.** In an audiobook, silence where a description should be sounds exactly like nothing having been there. A placeholder is less elegant to listen to and tells you the truth.

---

## Supported formats

**Works well:** EPUB, DOCX, ODT, HTML, plain text.

**Works, with the caveats above:** PDF, images, scanned documents.

**Works via conversion:** MOBI, AZW, AZW3, FB2, RTF, and other legacy formats. These require Calibre to be installed; Asoy calls it to convert them first.

**Not supported:** any DRM-protected file, in any format.

---

## Getting better results

- **Prefer EPUB** over PDF whenever the book exists in both.
- **Scan at a higher resolution** if you are scanning yourself. Text recognition quality tracks input quality closely, and no later step recovers what the scan lost.
- **Use the review screen.** Flagged descriptions and low-confidence pages are collected there. Correcting a handful before narration is far faster than re-recording afterward.
- **Convert one chapter first** when trying a new book, especially a heavily illustrated one. You will learn in minutes what would otherwise take hours.
- **Close other GPU-heavy applications** before a long conversion. Asoy will fall back to the CPU tier if video memory runs out mid-job, and it will tell you it did.

---

## Common problems

| What you see | What it means | What to do |
|---|---|---|
| "Ollama not found" | Ollama is not installed | Install it, then restart Asoy |
| "Ollama unreachable" | Installed but not running, or on a different port | Start Ollama; check its port setting |
| "Model not available" | The model has not been downloaded | Run the `ollama pull` command Asoy shows you |
| Switched to CPU tier partway through | Video memory ran out | Close other GPU applications; expected on smaller cards |
| Conversion is very slow | CPU tier, long book | Expected. It will resume if interrupted |
| Text garbled or missing | Scanned source, poor recognition | Check flagged pages in the review screen |
| Chapters out of order | Complex PDF layout | Use an EPUB if one exists |
| Vague chart descriptions | CPU tier, or a dense chart | Check your tier first |
| MOBI or AZW3 will not convert | Calibre missing, or the file has DRM | Install Calibre; check whether the file is protected |
| File rejected immediately | DRM, or a corrupt file | Read the message shown; DRM files cannot be converted |

---

## Reporting a problem

Include all of this in the first message. It saves several rounds.

- Asoy version.
- The hardware tier shown in the interface.
- Your GPU and its memory, if you have one. In a terminal: `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv`
- Your Ollama version, and the output of `ollama list`.
- Your Windows version.
- The source file's format and rough size.
- The job record and log file. Asoy shows you where these are.

**The logs contain no book text and no page images** — only file paths and technical details about processing. You can check this yourself; Asoy is open source.

**Please do not send the book.** It is rarely needed and raises copyright questions. If the problem depends on the specific file, try reproducing it with a public-domain book first.

---

## Things Asoy will not do

Answered here so the question does not need asking.

- **Send anything to a cloud service**, including for better descriptions. Everything stays on your machine. That is the point of the project, and it is also why descriptions are not as good as a large cloud model would produce.
- **Remove DRM**, or explain how to.
- **Collect usage data.** Asoy checks for new versions and sends nothing else. That check can be turned off.
- **Produce audio.** Asoy produces text prepared for narration. Turning that text into audio is your text-to-speech tool's job, and keeping the two separate means you can use whichever one you prefer.
- **Rewrite or improve the author's text.** Asoy transcribes it exactly, including its errors. Descriptions of visual content are the only text Asoy generates, and they are always marked as such.

---

*Asoy is free and open source under Apache 2.0. If something here is wrong or unclear, that is a bug worth reporting too.*
