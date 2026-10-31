# Review: US-7.2

Change: us-7-2-edit-export-draft
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | A NUL in the draft ended MuPDF's text, so the PDF silently lost everything after it; other control characters rendered as stray glyphs | Both formats drop the characters XML cannot hold before layout; `test_us_7_2_pdf_keeps_text_after_control_characters` |
| medium | Exports outlived a worker shutdown: a plaintext letter stayed on disk until the worker next started | `Exports.shutdown` deletes every export when the worker stops (a shutdown step in `create_app`); spec scenario "Exports go when the worker stops"; `test_us_7_2_worker_lifespan_sweeps_and_clears`, `test_us_7_2_clear_touches_exports_only` |
| low | Exports were not audited | `AuditAction.DRAFT_EXPORTED`, recorded after each export (IDs and times only); `test_us_7_2_export_is_audited` |
| low | MuPDF's HTML parser decoded entities a second time (`AT&amp;T` printed `AT&T`) | Paragraphs are built through the Story DOM; `test_us_7_2_entity_text_is_kept_as_written` |
| low | An edit saved between the route's busy check and a draft job's save was replaced by the job | `save_draft(started=…)` refuses, under the case lock, to replace a draft edited since the job started; the job ends `draft_edited` (new code, fixed message); spec scenario "An edit saved while drafting is kept"; `test_us_7_2_edits_saved_while_drafting_are_kept` |
| low | Draft again discarded unsaved editor text without a warning | Disabled while the editor holds unsaved text (shared with the US-7.1 finding) |
| low | A double-click on Export wrote two files and opened two save dialogs | One export at a time: the pane shows "Exporting the PDF…" and disables both buttons; node `one export at a time: the buttons wait for the answer` |
| low | `case-export` spliced `TO` into shell text and copied with umask permissions before `chmod`, overwriting an existing target | `TO` goes through the environment; the copy is created 0600 with `O_EXCL` (an existing target is refused); runbook updated |
| low | The lifespan sweep test patched a default that was already bound, so it checked only the first sweep | The test injects a short interval and writes the expired file after the first sweep; it also checks the shutdown clear |
| nit | `assert "Appeals" not in text` could never fail | Replaced by assertions on the indented and CRLF lines |

Also checked by the reviewer and found sound: the namespace SDK import and capturing the save action before the REST read; the gateway serving `plugin-data/claimcoach/exports/` through `/api/fs/download`; Electron downloading before the save dialog (no race with the 15-minute expiry); the strict `DraftEdit`, `ExportRequest`, `ExportedFile`; `Exports.write` (0600, `O_EXCL|O_NOFOLLOW`, temporary name and rename, cleanup on failure); the sweep touching export names only; the DOCX package; BR-1, BR-11, BR-12, BR-14. Characters outside the Basic Multilingual Plane were left UNVERIFIED by the reviewer (emoji extraction); the CJK and accented text in the tests reads back exactly.

## Re-verification

`make verify` → exit 0 on the fixed tree with all three EPIC-7 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1182 offline pytest tests passed at 100% line and
branch coverage of `plugin/`; 104 node tests at 100% line, branch, and function coverage of
`plugin.js`; evidence-check `ok` for every report through US-7.3 (OhMyOrch accepted each); 2 gate
self-tests passed. Evidence recorded by the independent `story-tester` after the fixes, including
operator runs of `make case-draft` (with and without `TEMPLATE=`), `case-show`, `case-edit`, and
`case-export FORMAT=pdf|docx TO=…` against scratch workers with fake models and synthetic data;
the exported files were read back with pdftotext, pdfinfo, textutil, and unzip. The real-model
test `test_us_7_1_draft_real_model` ran Ternary-Bonsai-2-27B from `~/Models` through
`ModelManager` and passed (43 s), after `--reasoning off` was added (without it the same test
failed `drafting_failed`); no model server was left running.
