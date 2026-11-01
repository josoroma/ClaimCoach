# Proposal: US-10.4 Global Corpus Import from the Settings Page

## Why

PRD §9 puts the global-corpus import on the settings page as well as the CLI. US-4.3 delivered the
bundle format, the worker's all-or-nothing `POST /corpus/import`, and `hermes claimcoach corpus
import`, and left the settings-page import to US-10.3, whose review deferred it: an import replaces
reference material for every profile on the Mac, so it needs a preview and a confirmation. Today a
manager needs a terminal (`make corpus-import`).

## What Changes

- `corpus/bundle.py`: `parse_bundle_bytes(data, filename)` (the checks `parse_bundle` makes, on
  bytes; `parse_bundle` now uses it); a problem's location keeps only known field names and item
  numbers. `BundlePreview`: whether the file is a valid bundle, the first problem, item counts per
  kind, payers, stale items, and which items replace ones already in the global corpus. YAML
  aliases are refused, and the gateway parses off its event loop.
- Gateway `POST /corpus/import/preview` (the picked file, single-file multipart; writes nothing)
  and `POST /corpus/import?confirm=true` (the same file; imports through the worker's existing
  route). Without `confirm=true` the import answers `import_not_confirmed`; an invalid bundle
  answers `invalid_bundle`.
- `WorkerClient.import_corpus` waits up to 15 minutes (the embedding model may load and embed
  thousands of chunks).
- Settings page: a Global corpus import section: pick a `.yaml`, `.yml`, or `.json` file (at most
  5 MiB), read the preview, then **Import into the global corpus** or **Cancel**; the outcome shows
  what was stored and the corpus section refreshes.

## Capabilities

### New Capabilities
- `corpus-import-page`: previewing and importing a global-corpus bundle from the settings page.

### Modified Capabilities
- None (`no-send-submit`'s pinned gateway routes gain the two import routes; `corpus-import` keeps
  its requirements: a local file only, all or nothing).

## Impact

- Two gateway routes; no worker change. The CLI's error text for an invalid bundle may show `…`
  where a key from the file stood.
