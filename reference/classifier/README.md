# Classifier reference set

The instrument that decides whether a change to the block classifier is an improvement. Without
it, "it looks better to me" is the only available evidence, which `CLAUDE.md` §9 names as a
mistake to avoid. See ADR-026.

**Status: empty. The images do not exist yet.** The manifest format and the harness are in place;
the books are being gathered. Every acceptance number for the classifier is unmeasured until this
directory holds the core set, and the acceptance test skips rather than reporting a vacuous pass.

---

## What goes in the core

Committed to this repository, so it must be public domain. About 60 picture blocks drawn from at
least four distinct books:

| Expected type | Roughly |
|---|---|
| `photograph` | 12–15 |
| `illustration` | 12–15 |
| `diagram` | 12–15 |
| `chart` | 12–15 |
| `unknown` | about 10, deliberately ambiguous |

The `unknown` entries are not filler. They are the ones that test the rule that a guess is worse
than an abstention, and without them a classifier that never abstains scores perfectly.

Four books minimum, because a set drawn from one book measures that book's engraver as much as it
measures the classifier.

## What goes in a local extension

Modern material — anything whose pages cannot be committed to a public Apache 2.0 repository.
Point `ASOY_REFERENCE_EXTENSION` at a directory holding its own `manifest.json` and images.

It is reported alongside the core and **never sets or moves the bar**. A threshold tuned against
material nobody else can see is not a threshold anyone can check.

## Manifest format

`manifest.json`, version 1:

```json
{
  "version": 1,
  "entries": [
    {
      "image": "images/rivers-of-france-112.png",
      "source": "rivers-of-france.epub",
      "locator": "picture[7]",
      "expected": "chart",
      "caption": "Fig. 14.—Discharge of the Loire, 1854-1861.",
      "context": "The following season was drier still, as the record shows.",
      "reasoning": "Plotted series against a labelled year axis. The caption names no type, so the pre-pass must abstain and the model call decides it."
    }
  ]
}
```

`image`, `source`, `locator`, `expected`, and `reasoning` are required. `caption` and `context`
are optional and default to empty.

**`reasoning` is one line and is not decoration.** It is what makes a disputed entry settleable
without re-reading the book, and writing it is where you find out that an entry you thought was a
`diagram` is arguable. If you cannot write the line, the entry belongs in the `unknown` group.

**`caption` and `context` must be what the parser would actually have supplied.** Leaving a real
caption out makes the pre-pass look useless; inventing one makes it look better than it is. Both
distort the figure the bar is read from.

## Running it

```
uv run pytest tests/test_classifier_reference.py -m reference -s
```

Requires Ollama running with the tier's model pulled, since it makes a real vision call per
block. It is excluded from the default suite for that reason — see `RUNBOOK.md` §9.
