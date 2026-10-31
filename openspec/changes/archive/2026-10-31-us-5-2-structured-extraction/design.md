# Design: US-5.2 structured extraction

## Context

US-5.1 stores a case's source files encrypted as case items. The `extraction` role in
`models.yaml` is Qwen3-VL-8B served by `mlx_vlm.server` (OpenAI-compatible, takes `image_url` data
URLs, and resolves the `model` field as a model path). Prompts must come from registered templates
with document content only inside data blocks (US-3.6). `broadcast_plugin_event` exists only in
the gateway process, while extraction runs in the worker (PC-4).

## Goals / Non-Goals

Goals: fill a typed `CaseExtraction` from PDFs, images, 835 text, and letter text; mark each field
`extracted`, `unreadable`, or `confirmed`; let the biller confirm a value; push progress events.

Non-Goals: classification and explanation (EPIC-6); adding or deleting claim lines by hand;
indexing extracted text for retrieval (EPIC-6 does what it needs).

## Decisions

1. **Every value is validated on its own.** The model's JSON (or the 835 reader's output) is a
   loose reading (`Reading`) that tolerates `null` lists, malformed items, and values of the
   wrong JSON type, which read as absent; each value goes through its typed validator (CARC `^\d{1,3}$` or
   letter+digits, RARC `M|MA|N` + digits, group code `CO|PR|OA|PI|CR`, procedure code, ISO date,
   money with 2 decimals). A missing or invalid value becomes `unreadable` with no value, so one
   bad field never loses the rest. Rejected: validating the whole reply at once, which turns one
   misread date into a failed case.
2. **835 text is parsed, not modelled.** X12 is exact; `edi835.py` reads delimiters from the ISA
   segment, takes `N1*PR`, the first `CLP` loop (claim, `CAS`, `MOA` remarks), and its `SVC`
   lines with `DTM*472`, `CAS`, and `LQ*HE`. Further claims are counted in `other_claims` and the
   pane says so. Rejected: sending 835 text to the 8B model, which is slower and less exact.
3. **PDF pages go to the model as images plus their text layer.** PyMuPDF renders each page at
   150 dpi (less when the longest side would pass 2000 px; at most 30 pages per PDF); the page's
   text layer, when present, is a second data item. Images are re-encoded as PNG, CMYK scans as
   RGB, halved until they fit 2000 px. A document that does not decode is listed in
   `unread_sources`, and the pane says so.
   Rejected: text layer only, which fails on scanned EOBs; image only, which throws away exact
   text a born-digital EOB carries.
4. **Field paths address confirmation.** `payer_name`, `lines.0.service_date`,
   `lines.0.adjustments.1.carc`, `lines.0.rarc_codes.0`. Confirming validates the value with the
   field's own type and stores it as `confirmed` (audited `field_confirmed`), under a per-case lock
   shared with storing an extraction. A re-run keeps confirmed claim-level values; values inside
   the lines are addressed by position, so they are kept only when the lines come from the same
   source (`itemized_by`) in the same number. Rejected: free-form JSON patches from the pane;
   keeping every confirmation by path, which can move a value onto another line.
5. **The worker produces events, the gateway broadcasts them.** A job appends `CaseProgressEvent`s
   (IDs, stage, fraction; no free text by construction, US-3.4) to an in-memory list.
   `POST /process` in the gateway starts the job, then one gateway task per job long-polls
   `GET /jobs/{id}/events?after=n` (20 s per poll) and calls `publish()` for each event. A job
   stops after 60 min (`processing_timeout`); the relay gives up 5 min after that, and after 3
   failed polls in a row; either way it publishes a `failed` event, so the pane never waits
   forever. Rejected: a worker → gateway callback (the gateway has no
   authenticated inbound route for the worker) and a pane poll loop (PC-4 says push).
6. **The pane listens with `ctx.onEvent`, not `host.onEvent`.** It is the same gateway event
   stream (SDK docs, "Pushing events to your desktop half"), retired with the plugin, and keeps
   US-3.3's rule that `plugin.js` never touches `host`. It is feature-detected (PC-3); without it
   the pane reopens the case when the biller presses Refresh.
7. **One job per case.** Starting extraction while a job for the case runs returns that job.
   Finished jobs are kept 10 minutes (at most 64) so a late poll still sees the end.
8. **Stages and codes.** `extracting` with progress up to 0.95 per page or document, then `done`
   at 1.0, or `failed` with `model_unavailable`, `model_busy`, `case_closed`, or
   `extraction_failed`. A document that cannot be opened (a corrupt PDF) is skipped and its fields
   stay unreadable; the job still finishes.

9. **Merging sources.** Claim-level values come from the first source that reads them; lines,
   adjustments, and remark codes all come from the first source that has any (835 text first,
   then in attach order), its pages concatenated. Rejected: concatenating every source, which
   duplicates the lines when the 835 and its EOB are both attached.
10. **A worker without models answers `model_unavailable`** for extraction (tests and a corpus-only
    worker), never a 500.

## Risks / Trade-offs

- [PyMuPDF is AGPL-3.0 (or commercial)] → it runs only in the app-owned worker venv; the license
  must be cleared before distribution, and `pypdfium2` (Apache-2.0) is the drop-in alternative
  for `rasterize_pdf`, which is the only function that imports it.
- [The model may invent a value] → only values that validate are kept; the biller sees every
  field and can correct any of them; drafts stay "for human review" (BR-4).
- [Events lost while the gateway restarts] → the case is the source of truth: reopening it shows
  the stored extraction.
- [Python 3.12 warns on PyMuPDF's SWIG types at import; under pytest's warnings-as-errors that
  crashes the interpreter] → `pyproject.toml` ignores exactly that warning.
- [Real-model accuracy is unmeasured here] → `test_us_5_2_extraction_fills_case` is marked
  `models` and runs against Qwen3-VL-8B when its weights are present.
