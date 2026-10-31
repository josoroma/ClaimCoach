# Review: US-5.1

Change: us-5-1-case-intake
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | After any unexplained failure (including a reopen that failed after a successful upload) the pane forgot the open case, so the next drop created a second case and stranded the first one's PHI | The pane remembers the last case it worked on (`life.caseId`) across failures; `addDocument` returns `unavailable` with the case ID once the case exists, and Refresh reopens it; `a case whose reopen fails stays the open case for the next drop` |
| medium | A drop uploaded only `files[0]`; the EOB and letter dropped together lost the letter silently | `addFiles` uploads every dropped or picked file into one case, in order, and stops at the first refusal; `two files dropped together go into one case, in order`, `a refused file stops the rest of a multi-file drop` |
| medium | Cases the pane leaves are never closed, so retention never starts for them; Process was enabled without a `/process` route | `/process` ships in US-5.2. Cases close with an outcome (US-8.1) and the case list is US-10.1: recorded as a design risk with the runbook's `corpus-audit` step to find open cases and purge them on request |
| low | No size check before `file.arrayBuffer()` | `addFile` refuses files over 16 MiB before reading them, with the fixed `document_too_large` notice; `a file over 16 MiB is refused before it is read` |
| low | A 413 sent before the body is read may reach a webview as a reset | Mitigated by the pane-side size check; recorded as a design risk |
| low | The paste box was cleared before the attach finished | A paste that was not attached goes back into the box; `a paste that is not attached goes back into the box` |
| low | A closed case given an unsupported or blank document answered 415 instead of `case_closed` | `CaseService` checks the case is open before reading the bytes; `test_us_5_1_closed_case_wins_over_the_file_check` |
| low | `%PDF-` had to be at byte 0 | The header is found anywhere in the first 1024 bytes, as PDF readers do; `test_us_5_1_pdf_header_after_a_prefix` |
| low | No route test sent a real over-limit file part or a streamed body without `Content-Length`; the open-case pane test used the file input, not a drop | `test_us_5_1_oversized_file_part_refused_by_the_worker`, `test_us_5_1_streamed_oversized_body_refused`; `test_us_5_1_pane_drop_adds_to_the_open_case` now drops |
| low | `POST /cases` read its JSON body unbounded | `CaseCreate`, process, and field bodies are read with a 64 KiB bound; `test_us_5_1_small_bodies_are_bounded` |
| info | `tasks.md` and the proposal named a test and a runbook that do not exist; evidence not recorded yet | Names fixed; evidence recorded in `evidence/US-5.1/` |

## Re-verification

`make verify` → exit 0 on the fixed tree (2026-10-31): ruff, ruff format, biome, mypy --strict ×2,
tsc --checkJs; 976 offline pytest tests passed at 100% line and branch coverage of `plugin/`; node
tests at 100% line, branch, and function coverage of `plugin.js`; evidence-check `ok` for every
report through US-5.2 (OhMyOrch accepted each); 2 gate self-tests passed. Evidence recorded by the
independent `story-tester` after the fixes, including an operator run of the `make case-*` targets
against a scratch worker (no Keychain item, no real patient data).
