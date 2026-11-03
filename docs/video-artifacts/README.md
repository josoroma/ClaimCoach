# ClaimCoach English product walkthrough

Prepared for prospective users and Y Combinator reviewers on 2 November 2026.
This is a product walkthrough, with no claim of YC affiliation or acceptance.
The video uses actual Hermes Desktop captures, a fictional denial case, and
English narration generated locally with `chatterbox-multilingual-v3`.

## Deliverables

- [Watch the English video](film/claimcoach-walkthrough.en.mp4)
- [Film and reproduction instructions](film/README.md)
- [English script](film/script.en.json) and [subtitles](film/claimcoach.en.srt)
- [Narration provenance and validation](audio/README.md)
- [Fictional input documents and payer rules](demo-inputs/README.md)
- [Actual exported PDF](outputs/claimcoach-demo-appeal.pdf) and
  [DOCX](outputs/claimcoach-demo-appeal.docx)
- [Export verification](outputs/export-receipt.json)
- [Model findings and limitations](quality-review.md)

## Production plan and evidence

The walkthrough follows ten scenes: introduce the problem; enable the plugin;
connect the local model; add a denial; check extracted facts; diagnose; edit and
export a draft; use the command and skill; explain the agent loop; close with
the biller's next step. The interactive HTML composition and video renderer use
the local `/Users/josoroma/sites/taster` workflow. All scenes share the same
script, recorded screenshots, audio timing and captions.

Before capture, the dedicated Hermes workspace was configured and the plugin
enabled. The actual worker imported the fictional reference corpus, parsed the
835, ran local classification and explanation, generated a draft, saved the
operator's corrections and exported both formats. The original model output is
preserved in `outputs/case-original-model-result.json`; the corrected draft is
still marked for human review.

The canonical [agent-loop receipt](agent-loop.json) records the local model
loading `claimcoach:denial-triage`, discovering tools, and calling all three
ClaimCoach handlers successfully. [The response](agent-responses.md),
[/denial command receipt](command-receipt.json), and
[local route audit](local-routing.json) provide separate evidence. The video
compresses elapsed processing time through edited screenshots and animation.
The subsequently captured [Desktop run](desktop-agent-loop.json) also finished
all three plugin tools. It corrected a malformed payer-rule call after Hermes
returned argument validation; the failed attempt remains visible in the capture.

## Reopen the configured workspace

From the repository root:

```sh
python3 docs/video-artifacts/runtime/workspace.py start
```

See [runtime instructions](runtime/README.md) for the existing local model
server dependency, isolated state, exact model adapters and useful commands.
Hermes v0.22.6 was already current. The demonstrated laptop is an Apple M3 Pro
with 36 GiB RAM, using installed ternary Bonsai 27B text weights and Qwen3
Embedding 8B weights under `~/Models`. No cloud model fallback is configured.

Vision and transcription weights are missing, so this run validates 835 text
intake, not OCR or call transcription. Memory pressure required unloading the
embedding model before retrying drafting. The initial model made unsupported
claims; this demonstration establishes integration behavior, not clinical or
billing accuracy, appeal success, a privacy certification, or performance on
every consumer laptop. No appeal was submitted and no outcome was invented.

The standalone production helpers are outside the application Ruff gate.
Their syntax, actual execution, audio checks, film checks and export checks are
recorded alongside the artifacts. Application lint, types and coverage remain
covered by `make check`. The final gate passed: 1,876 Python tests passed
(one skipped, 14 deselected) and 191 JavaScript tests passed, with 100%
application coverage. See
[the complete check log](application-check.log) and
[the standalone artifact audit](artifact-audit.json).
