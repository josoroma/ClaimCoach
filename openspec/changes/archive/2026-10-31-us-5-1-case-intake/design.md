# Design: US-5.1 case intake

## Context

The pane already calls `POST /cases`, `POST /cases/{id}/documents` (a `ctx.rest` upload, which
Hermes sends as `multipart/form-data` with one part named `file`), and `GET /cases/{id}` (US-3.3).
The user scope (US-4.1, US-4.2) is an encrypted SQLite store per profile that holds cases,
documents with chunks and vectors, outcomes, and the audit log. Storing a `Document` needs its text
and embeddings, and an uploaded PDF or image has no text until extraction (US-5.2) runs.

## Goals / Non-Goals

Goals: create a case; attach a PDF, PNG, JPEG, or text file; attach pasted 835 text; list the
case's source documents; keep every byte encrypted at rest and inside the retention purge.

Non-Goals: extraction (US-5.2); indexing source text for retrieval (EPIC-6 indexes the extracted
text it needs); removing a single document; listing all cases (US-10.1).

## Decisions

1. **Source files are case items, not corpus documents.** A new `case_items` table holds each
   source as a sealed JSON payload (`SourceDocument`) plus the sealed bytes, keyed by
   `(case_id, item_id)`, with associated data `case_items:<case>:<item>`. Rejected: storing the
   file as a `Document` — it needs text and vectors at upload time, which would load the 8B
   embedding model for every drop and index unreadable bytes.
2. **Kind comes from the bytes.** `%PDF-` → `pdf`; PNG or JPEG signatures → `image`; strict
   UTF-8 → `text`, or `edi_835` when it opens with an `ISA` segment and holds `ST*835`. The
   declared content type and the filename are kept for display only. Rejected: trusting the
   content type, which the browser derives from the extension.
3. **Open question resolved (formats and size):** PDF, PNG, JPEG, and UTF-8 text files; at most
   16 MiB per file (a 20-page scanned EOB at 150 dpi is ~10 MiB) and 4 MiB of pasted text (PC-3's
   `ctx.files` figure, more than any single-claim 835). Anything else is `unsupported_document`
   (415); too large is `document_too_large` (413). Rejected: HEIC/TIFF, which Qwen3-VL's
   processor does not take without conversion.
4. **The gateway forwards the multipart body unparsed.** It reads at most the limit plus 64 KiB of
   framing into memory and sends it to the worker with its content type; the worker parses the
   single `file` part in memory (`cases/intake.py`). Rejected: Starlette's form parser, which
   spools parts over 1 MiB to an unencrypted temporary file, and parsing in the gateway (PC-4: it
   only proxies).
5. **Case IDs are `new_case_id()`** (`case_` + 16 hex digits), the pattern events already accept,
   so a case can be named in a progress event. The gateway passes `active_profile()`; case
   creation is the only call that creates a profile's user scope.
6. **A closed or purged case takes no new documents** (`case_closed`, 409): its retention clock
   has started, and a purged case must stay empty.
7. **The pane is the drop zone.** Dropping or picking a file adds it to the open case, or creates
   one first; "New case" starts over. The paste box attaches its text to the open case the same
   way. Rejected: a separate drop target element, which would shift the pane's controls without
   adding anything.

## Risks / Trade-offs

- [A 16 MiB upload sits in gateway and worker memory] → bounded reads; one upload at a time per
  pane; documented in the runbook.
- [The filename may be PHI] → stored only inside the sealed payload, returned only to the pane,
  never logged; IDs in responses and audit entries are opaque.
- [Source bytes are not searchable until extraction] → intended; retrieval (BR-5) works on the
  extracted text EPIC-6 indexes.
- [A case the pane leaves (New case, a reload) stays open, so retention (BR-7) never starts for
  it] → cases close when an outcome is recorded (US-8.1) and the case list arrives in US-10.1;
  until then the runbook shows how to find open cases (`corpus-audit`) and purge them on request.
- [`multipart/form-data` is a CORS-simple type] → an upload needs the random 64-bit case ID and
  passes Hermes' own gateway authentication; it can only add a document to an existing case.
- [The gateway answers an oversized `Content-Length` with 413 before reading the body; a webview
  may see a reset instead] → the pane refuses files over 16 MiB before reading them, so a biller
  sees the fixed too-large message either way.
