# Review: US-10.3

Change: us-10-3-settings-page
Reviewer: independent `story-reviewer` agent (read-only, given the three EPIC-10 change names and changed files, not the implementer's reasoning), 2026-10-31, with probes against the real Hermes v0.22.5 writer; independent `story-tester` operator run (scratch worker plus `plugin_api.py` in Hermes' own Python; a purge at the newly saved period)
Verdict: pass after fixes; the global-corpus import UI is deferred (recorded below)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | `GET /settings` read `retention_days` through the all-or-nothing `load_settings`, so one other invalid key made the page show 90 while the worker purged at the stored 30 (and a stored 5000, which the worker skips, also showed 90) | `stored_retention_days` validates the value on its own, exactly as `load_retention_days` does (shared `_retention_of`); an invalid value answers `null` and the page says no closed case is purged until a valid period is saved. Design decision 6; `test_us_10_3_page_shows_the_period_the_purge_uses` (4 cases), `test_us_10_3_outside_hermes_the_default_period_is_shown`, node "an invalid stored period says purges are skipped and takes a new one" |
| medium | Hermes' writer raises parser, runtime, and OS errors that escaped the route as a plain-text 500 whose traceback quoted config lines (a secret in the probe) | Every error from the writer is a fixed envelope, logged by type only and raised `from None`. Design decision 7; `test_us_10_3_a_failed_save_is_an_envelope_without_its_text` (3 errors), `test_us_10_3_malformed_config_with_hermes` (`hermes` marker, the real writer and a malformed `config.yaml`) |
| medium | US-4.3 left the global-corpus import UI to this page; the change neither built it nor said so | Deferred and recorded: design Non-Goals (a manager-wide import needs its own confirmation design, BR-1) and an open question on US-10.3 in SPECS.md; `make corpus-import` remains the path. Offered as a follow-up story |
| low | Every `PermissionError` read as `settings_managed`, including an unreadable `config.yaml` | Only a `PermissionError` without an errno (Hermes' managed refusals) is `settings_managed`; others are `settings_unavailable`. `test_us_10_3_a_failed_save_is_an_envelope_without_its_text[PermissionError]`, `test_us_10_3_hermes_refuses_the_save` |
| low | The worker opened every profile's store (and Keychain key) for the page's corpus section | `GET /corpus/status?profile=` reports only that profile's scope; the gateway passes the active profile. Design decision 8; `test_us_10_3_worker_reports_only_the_asked_profile` (only one key is asked for) |
| low | A save waiting on Hermes' config lock had no limit | `SAVE_TIMEOUT` (30 s) answers `settings_unavailable`; `test_us_10_3_a_save_stuck_on_the_config_lock_times_out` |

Also checked by the reviewer and found sound: `RetentionUpdate` (strict, `extra="forbid"`, 1-3650), the 422 and 413 envelopes, nothing written on refusal; `PLUGIN_DIR` is the `plugin.yaml` Hermes validates against; the route pins and the Hermes import allow-list; BR-1 (no new outbound call); the page's independent sections, a save winning over a late first read, and fixed text per refusal code; the feature-detected `registerSettingsPage`.

## Re-verification

`make verify` on the tree holding all four EPIC-10 and EPIC-11 changes:

```text
$ make verify
All checks passed!
TOTAL    7102      0   1180      0   100%
Required test coverage of 100.0% reached. Total coverage: 100.00%
=============== 1544 passed, 10 deselected in 181.17s (0:03:01) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
ok   US-10.1
ok   US-10.2
ok   US-10.3
ok   US-11.1
================ 2 passed, 1552 deselected in 186.42s (0:03:06) ================
```

The `hermes`-marked tests (`test_us_10_3_retention_saved_with_hermes`, `test_us_10_3_malformed_config_with_hermes`) run inside `make check` against the local Hermes v0.22.5 and pass.
