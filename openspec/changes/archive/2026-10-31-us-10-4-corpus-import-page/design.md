# Design: US-10.4 global corpus import from the settings page

## Context

`CorpusBundle` (US-4.3) validates a whole bundle: tagged items with `source` and `verified_on`,
unique keys, one spelling per payer, at most 5000 items and 5 MiB of text. The worker's
`POST /corpus/import` stores all of it or none, re-embedding the chunks with the `embedding` role;
an item whose key exists replaces it. `GET /corpus/global` lists the stored items by kind and key.
The settings page (US-10.3) loads its sections on its own and reaches the backend only through
`ctx.rest` (BR-2). `ctx.rest` can send one file as `multipart/form-data` (`upload`).

## Goals / Non-Goals

Goals: a manager imports a local bundle from the settings page after seeing what it holds and what
it replaces; an invalid file is explained; nothing is written without an explicit confirmation.

Non-Goals: editing or deleting single global items; importing from a URL (BR-1: local files only);
roles (Hermes profiles have none: whoever opens the page on the Mac acts as the manager, as for the
CLI in US-4.3).

## Decisions

1. **Preview, then import the same file again.** The pane keeps the picked file's bytes, uploads
   them to `POST /corpus/import/preview`, shows the answer, and on **Import into the global
   corpus** uploads the same bytes to `POST /corpus/import?confirm=true`. The gateway parses and
   validates both times, so no state is held between the two requests. Rejected: a server-side
   preview token (state to expire and clean up for a 5 MiB file the pane already holds).
2. **Confirmation is part of the request.** Without `confirm=true` the import route answers
   `import_not_confirmed` (409) and sends nothing to the worker, so a stray request (a script, a
   retried call) cannot import. The upload is `multipart/form-data` with a `file` part only, so the
   flag is a query parameter. The flag is not a cross-site defence: a page that can reach the
   gateway could add it. Hermes' gateway authentication (the `X-Hermes-Session-Token` header on
   loopback, the `SameSite=Lax` cookie when the gate is on) is what keeps other sites out, as for
   the US-5.1 and US-11.1 uploads (review finding).
3. **The preview says what will change.** Counts per kind, the payers named by rule cards (at most
   50), stale items (verified more than 180 days ago), and which keys already exist in the global
   corpus (read with `GET /corpus/global`) and will be replaced, named as `<kind> <key>` (at most
   50, then a count). A worker that is down answers the
   preview with `worker_unavailable`: the import would fail too.
4. **An invalid file is a valid answer, not an error.** The preview answers `valid: false` with the
   first problem (`invalid bundle at items.3.rule_card.payer: string_pattern_mismatch`), so the
   manager can fix the file. Bundles are reference material, not PHI; still, a location keeps only
   field names ClaimCoach defines and positions in its lists (`items`, `required_documents`), and
   any other part (a key the file invented, a number used as a key) shows as `…`, so file text is
   never echoed. A whole-bundle problem adds ClaimCoach's own fixed reason ("duplicate item key in
   bundle"). The import route answers an invalid file with the
   fixed `invalid_bundle` envelope.
5. **Limits are checked before reading.** The pane refuses a file over 5 MiB before reading it; the
   gateway reads at most 5 MiB plus framing.
6. **The import may take minutes.** `WorkerClient.import_corpus` waits up to 15 minutes, and the
   pane's request waits a minute longer so the gateway answers first. A gateway that gives up
   answers `worker_unavailable`, yet the worker may still commit: after any import attempt the
   corpus section is read again, and a timed-out or unclear failure says the import may still be
   finishing. A failed import keeps the file's bytes for **Try again** (review findings).
7. **Parsing stays off Hermes' event loop.** Hermes serves the desktop and every plugin from the
   gateway process, so the bundle is parsed in a worker thread with libyaml's safe loader when it
   is built in (seconds instead of half a minute on a nested 5 MiB file), and YAML aliases are
   refused, so a small file cannot expand to gigabytes in memory (review finding).
8. **The file picker always reacts.** The input is cleared after each pick, so picking the same
   file again (after a fix, a Cancel, or a refusal) previews it again (review finding).

## Risks / Trade-offs

- [The global corpus changes for every profile at once] → the preview names how many items are
  replaced, and the button says "into the global corpus"; `make corpus-backup` before a large
  import is in the runbook.
- [The file may change between preview and import] → the import validates it again; the outcome
  shows what was stored.
- [Two managers import at once] → the worker imports one bundle at a time (its write lock); each
  import is all or nothing.
