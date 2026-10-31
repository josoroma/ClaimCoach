---
name: deliver-story
description: Deliver one or more ClaimCoach user stories (US-x.y) or a whole EPIC from SPECS.md through OpenSpec changes, with tests at 100% coverage, evidence reports, an independent review, and archive. Use when asked to implement, deliver, or ship a story or epic of this project.
argument-hint: US-x.y | EPIC-n
---

# Deliver a ClaimCoach story through OpenSpec

The project is its own evidence: every story leaves an archived OpenSpec change, tests named after
its Gherkin scenarios, a test report, JUnit XML, and a review record. EPIC-1 is the reference —
read `openspec/changes/archive/2026-10-30-us-1-2-worker-sidecar/` before the first story of a
session. Conventions are in [references/conventions.md](references/conventions.md).

Target: `$ARGUMENTS`. For an EPIC, deliver its stories in dependency order (SPECS.md
"Dependencies:"), one change per story.

## 1. Read the story

- `SPECS.md`: the story section (`### US-x.y`), its Gherkin, Tasks, Open Questions, and the
  Global Business Rules / NFRs it cites. `PRD.md` for the cited sections.
- Existing code the story extends. Never duplicate what EPIC-1 already provides
  (`WorkerClient`, `envelope()`, `WorkerConfig`, `app_data_dir()`, the fake model server, the
  socket guard).
- Resolve each Open Question with a stated default; record it as a design decision, not silently.

## 2. Open the change

```bash
openspec new change us-<epic>-<n>-<slug>
```

Write `proposal.md`, `design.md` (when there is a real decision), `specs/<capability>/spec.md`
(ADDED/MODIFIED Requirements, each with `#### Scenario:` blocks mirroring the Gherkin), and
`tasks.md` (each task ends with how it is verified). Then:

```bash
openspec validate us-<epic>-<n>-<slug> --strict
```

## 3. Implement

- Module docstring lists the story and rule IDs it implements (ES-3). Google-style docstrings.
- Pydantic v2 `extra="forbid", frozen=True` for every config file, REST body, and result (ES-1).
- REST routes return a typed model or `envelope(code)`; error messages are fixed strings (ES-8,
  BR-14). Add new `ErrorCode`s to `claimcoach/api/models.py` with a fixed message.
- No bare `except`; no network outside loopback in offline code paths (BR-1).
- Subprocesses: fixed argv, no shell, `stdin=DEVNULL`, logs mode 0600, `start_new_session=True`.

## 4. Test

- One test per Gherkin scenario, named `test_us_<epic>_<n>_<slug>` in
  `tests/test_us_<epic>_<n>_<topic>.py`, under a `# --- Scenario: <name> ---` banner.
- Offline only: fakes in `tests/fakes/`, the fake OpenAI-compatible server, `tmp_path` for
  `MODELS_HOME` and data dirs. Real models are `@pytest.mark.models`.
- 100% line + branch coverage of `plugin/` is the bar; `# pragma: no cover` is forbidden
  (`test_us_1_4_no_coverage_exclusions`).

```bash
make check
```

## 5. Evidence

```bash
make evidence STORY=US-x.y
```

Copy `evidence/TEMPLATE/test-report.md` to `evidence/US-x.y/test-report.md`. One row per Gherkin
scenario, quoted; `PASS` only for what a named test or command actually exercised, otherwise
`UNVERIFIED` with the reason in Notes. Paste the real command output. Delegate an independent run
to the `story-tester` agent when the story has operator commands (Makefile targets, CLI).

## 6. Independent review

Launch the `story-reviewer` agent with the change name and the list of changed files only — not
your reasoning. Fix every finding with a regression test, then write
`openspec/changes/<change>/review.md` (Findings and resolution table, Re-verification with the
`make verify` result).

## 7. Close

```bash
make verify
openspec archive us-<epic>-<n>-<slug> --yes
make openspec-validate
```

Mark the change's tasks `[x]` before archiving. Runbooks touched by the story keep the four
sections Preconditions, Steps, Verification, Rollback (`test_us_1_5_runbooks_have_sections`).
Commit only when the user asks.
