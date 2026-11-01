# Review: US-10.4

Change: us-10-4-corpus-import-page
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, with benchmarks and probes of the gateway parse; independent `story-tester` operator run (scratch worker plus `plugin_api.py` in Hermes' own Python, driven by the page's own loaders)
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium (tester FAIL) | The Gherkin says the page shows *which* global items a bundle replaces; the preview gave only a count (design decision 3 had narrowed it) | `BundlePreview.replaced` names them as `<kind> <key>` (at most 50, `replaces` keeps the count); the page shows "Replaces: rule card Aetna/timely_filing, …". `test_us_10_4_bundle_previewed`, `test_us_10_4_replaced_items_are_capped`, node `test_us_10_4_pane_bundle_previewed`, "the replaced items are named, kind by kind" |
| medium-high | YAML parsing and validation of up to 5 MiB ran synchronously in Hermes' event loop (33 s measured for a nested 5 MiB file with the pure-Python loader); YAML aliases multiplied one string into a 1.1 GB peak | The parse runs in a worker thread with libyaml's safe loader when built in, and aliases are refused. Design decision 7; `test_us_10_4_parsing_does_not_block_the_gateway`, `test_us_10_4_yaml_aliases_are_refused` |
| medium | The file input was never cleared, so picking the same file again (after a fix, a Cancel, or "pick the file again") did nothing; a failed import had no retry | The input is cleared after each pick; a failed import keeps the bytes for **Try again**. Design decisions 6 and 8; node "picking the same file again is a change", "a failed import keeps the file for Try again and refreshes the corpus", "a failed preview offers no Try again" |
| low-medium | A gateway timeout read as "worker not running" or "not imported" while the worker could still commit the bundle | The pane waits a minute longer than the gateway; a timed-out or unclear import failure says it may still be finishing, and the corpus section is read again after any import attempt. Design decision 6; node "a refused or failed import explains itself with fixed text", "the pane waits longer than the gateway" |
| low | Whole-bundle problems read "invalid bundle at bundle: value_error" | A `value_error` carries ClaimCoach's own fixed reason ("duplicate item key in bundle", "a payer is spelled two ways in the bundle", …). `test_us_10_4_whole_bundle_problems_say_why`; `test_us_4_3_bundle_refusals` updated |
| low | Integer mapping keys the file invented were echoed in a problem's location | A number is kept only as a position in `items` or `required_documents`; any other is `…`. `test_us_10_4_invented_number_keys_are_not_echoed` |
| low (doc) | Design decision 2 claimed `confirm=true` stops cross-site requests | Corrected: the flag stops stray requests; Hermes' gateway authentication keeps other sites out, as for the US-5.1 and US-11.1 uploads |
| low (doc) | The runbook said the corpus count rises after any import | It rises by the number of new keys; replaced items leave it as it was |

Also checked by the reviewer and found sound: `parse_bundle` delegating to `parse_bundle_bytes` with the FIFO and size bounds kept; `BundlePreview` strict and frozen; `(kind, key)` matching the worker's `kind:key` document IDs; the confirmation checked before the body is read; `read_limited` refusing an oversized `Content-Length` first; every outcome a typed model or the envelope; fixed messages for `invalid_bundle` and `import_not_confirmed`; `IMPORT_TIMEOUT` with `trust_env=False`; the page's defensive parsing, size check before reading, last-pick-wins, unmount guards, fixed refusal texts, no new host access; the Hermes `ctx.rest` upload (one `file` part, `timeoutMs` honoured, bytes reusable); route pins; tests that drive a real gateway over a real worker.

## Re-verification

The tester re-ran the operator harness after the fixes and set the report to pass (4/4 criteria;
the first run's row-1 FAIL is kept under History in its Notes). Then:

```text
$ make verify
TOTAL    7197      0   1194      0   100%
Required test coverage of 100.0% reached. Total coverage: 100.00%
=============== 1569 passed, 10 deselected in 185.19s (0:03:05) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
ok   US-10.4
================ 2 passed, 1577 deselected in 189.36s (0:03:09) ================
```
