# Test Report: US-9.3 Denial-Triage Skill

Change: us-9-3-denial-triage-skill
Story: US-9.3
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (2026.9.24), gateway venv `~/.hermes/hermes-agent/venv`

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Skill is registered under the plugin namespace: Given the plugin is enabled, When the agent loads skill_view("claimcoach:denial-triage"), Then the skill content is returned" | PASS | `test_us_9_3_real_hermes_skill_view` (hermes-marked, ran in both the full `-k` run and `make agent-probe`). It loads the plugin into the installed Hermes Agent v0.22.5 with a throwaway `HERMES_HOME` whose `config.yaml` enables `claimcoach`, then calls Hermes' own `tools.skills_tool.skill_view("claimcoach:denial-triage")`. I also ran `tests/hermes/probe_agent.py` myself under the Hermes venv with my own throwaway home. Result: `success: True`, `name: claimcoach:denial-triage`, `readiness_status: available`, `skill_dir` = `<repo>/plugin/skills/denial-triage`. The content is 3771 characters: Hermes' one-line `[Bundle context: This skill is part of the 'claimcoach' plugin.]` header followed by the whole of `SKILL.md` (`content.endswith(SKILL.md)` is True). Also `test_us_9_3_skill_registered`: `register_skills` registers the bare name `denial-triage`, which comes out as `claimcoach:denial-triage` with the file's frontmatter and description. And `test_us_9_3_frontmatter_errors` (4 cases). Operator: `make agent-tools` lists `skill: claimcoach:denial-triage`. `make agent-skill` prints the header line and then `SKILL.md` unchanged (the same bytes plus `print`'s trailing newline) |
| 2 | "Skill content contains no PHI: Given the skill files, When the PHI detector scans them, Then no PHI span is found" | PASS | `test_us_9_3_skill_contains_no_phi`. It runs the US-3.1 `PhiDetector` (regex validators plus the model step over a fake PHI model that knows every fixture name and address), `find_regex_spans`, and `leaked_strings` over every file in `plugin/skills/denial-triage/` (one file only: `SKILL.md`). All three return `[]`, and the model step was called. I also ran my own scan (`scan_skill.py`). Its controls, run first: `find_regex_spans` finds 5 spans in fixture document 0, and the detector finds 16. Over `SKILL.md` (3705 characters): `find_regex_spans=[]`, `detector=[]`, and no whole-word match for any of the 114 seeded PHI strings of the 12 fixture documents. The only substring matches were the two-letter surnames `Li` and `Ng`, inside ordinary words (`billing`, `likelihood`, `filing`, `limit`, `anything`). Neither occurs as a word. Also `test_us_9_3_playbook_keeps_the_phi_boundary`: the playbook says to work only with case IDs, codes, and payer names, never to ask for a pasted EOB, and that ClaimCoach never sends or submits |

## Evidence Commands

```bash
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_9_3 or us_9_4" -v
make evidence STORY=US-9.3
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models
make agent-tools
make agent-skill > <scratch>/agent-skill.out          # compared with plugin/skills/denial-triage/SKILL.md
PYTHONPATH=<repo> uv run python -W ignore <scratch>/bin/scan_skill.py   # US-3.1 validators + detector + seeded strings
make agent-probe                                      # with HERMES_HOME/MODELS_HOME still pointing at <scratch>
# the probe by hand, with a throwaway home of my own:
mkdir -p <scratch>/probe-home/plugins; ln -s <repo>/plugin <scratch>/probe-home/plugins/claimcoach
printf 'plugins:\n  enabled:\n  - claimcoach\n' > <scratch>/probe-home/config.yaml
cd <scratch>/probe-cwd && HERMES_HOME=<scratch>/probe-home PYTHONPATH=~/.hermes/hermes-agent \
  ~/.hermes/hermes-agent/venv/bin/python <repo>/tests/hermes/probe_agent.py "Avery Vandermeer"
make evidence-check
```

```text
$ uv run pytest ... -k "us_9_3 or us_9_4" -v
collected 1406 items / 1384 deselected / 22 selected
tests/test_us_9_3_skill.py::test_us_9_3_skill_registered PASSED
tests/test_us_9_3_skill.py::test_us_9_3_real_hermes_skill_view PASSED
tests/test_us_9_3_skill.py::test_us_9_3_frontmatter_errors[# no frontmatter\n-ValueError] PASSED
tests/test_us_9_3_skill.py::test_us_9_3_frontmatter_errors[-ValueError] PASSED
tests/test_us_9_3_skill.py::test_us_9_3_frontmatter_errors[---\nname: x\n-ValueError] PASSED
tests/test_us_9_3_skill.py::test_us_9_3_frontmatter_errors[---\n- a list\n---\nbody\n-TypeError] PASSED
tests/test_us_9_3_skill.py::test_us_9_3_skill_contains_no_phi PASSED
tests/test_us_9_3_skill.py::test_us_9_3_playbook_keeps_the_phi_boundary PASSED
tests/test_us_9_3_skill.py::test_us_9_3_cli_prints_the_skill PASSED
===================== 22 passed, 1384 deselected in 7.19s ======================

$ make evidence STORY=US-9.3
collected 1406 items / 1397 deselected / 9 selected
tests/test_us_9_3_skill.py .........                                     [100%]
- generated xml file: .../evidence/US-9.3/junit.xml -
====================== 9 passed, 1397 deselected in 2.20s ======================

$ make agent-tools        (exit 0; tool lines trimmed)
claimcoach_explain_code  (toolset claimcoach, result ExplainCodeResult)
claimcoach_payer_rules  (toolset claimcoach, result PayerRulesResult)
claimcoach_case_summary  (toolset claimcoach, result CaseSummaryResult)
skill: claimcoach:denial-triage  (<repo>/plugin/skills/denial-triage/SKILL.md)
command: /denial [case ID]

$ make agent-skill        (exit 0, 67 lines)
# claimcoach:denial-triage  (<repo>/plugin/skills/denial-triage/SKILL.md)
---
name: denial-triage
description: Triage a denied medical claim and explain it to a biller with ClaimCoach's PHI-free tools (case IDs, codes, and payer names only).
version: 1.0.0
identical except print newline: True

$ scan_skill.py
files: ['plugin/skills/denial-triage/SKILL.md']
seeded PHI strings across 12 fixture documents: 114
control: regex spans in PHI_DOCUMENTS[0]: 5
control: detector spans in PHI_DOCUMENTS[0]: 16
plugin/skills/denial-triage/SKILL.md: 3705 chars; find_regex_spans=[]; detector=[]; seeded whole-word=[]; seeded substrings=['Li', 'Ng']
$ grep -ciE "\bli\b|\bng\b" SKILL.md   -> 0   (substring hits are inside billing, likelihood, filing, limit, anything)

$ make agent-probe
collected 41 items / 36 deselected / 5 selected
tests/test_us_1_1_plugin_package.py ...                                  [ 60%]
tests/test_us_9_3_skill.py .                                             [ 80%]
tests/test_us_9_4_denial_command.py .                                    [100%]
====================== 5 passed, 36 deselected in 40.47s =======================

$ probe_agent.py "Avery Vandermeer"   (Hermes v0.22.5 gateway venv, exit 0)
skill: {'success': True, 'name': 'claimcoach:denial-triage', 'readiness_status': 'available',
        'skill_dir': '<repo>/plugin/skills/denial-triage'} content chars: 3771
content ends with SKILL.md: True | first line: [Bundle context: This skill is part of the 'claimcoach' plugin.]
PHI whole-word in whole probe payload: []
```

Artifacts: `evidence/US-9.3/junit.xml`

## Failures

None.

## Notes

- `<scratch>` is
  `/private/tmp/claude-501/-Users-josoroma--claude-spares-spare-i9ct8L/90cb4ea0-d570-4856-9f3d-2969046d7edd/scratchpad/tester-b`,
  and `<repo>` is `/Users/josoroma/sites/ycombinator/claimcoach`.
- Isolation: every operator command ran with `HERMES_HOME` and `MODELS_HOME` under `<scratch>`.
  The Hermes probes (`make agent-probe` and my own run) each used a throwaway home with
  `plugins/claimcoach` linked to `<repo>/plugin`. `~/.hermes/config.yaml` has the same mtime and
  SHA-1 (`50907efc…`) before and after. `~/.hermes/plugins` is still empty, and
  `~/.hermes/plugin-data/claimcoach` was last changed at 09:32, before this run. Running the
  probe may have written bytecode caches under `~/.hermes/hermes-agent` (accepted by the task).
  No model was downloaded.
- "Given the plugin is enabled" was set up the way Hermes does it: `plugins.enabled: [claimcoach]`
  in the home's `config.yaml`, then `discover_plugins(force=True)`. Hermes' `/skills` UI and an
  LLM-driven `skill_view` call in a live chat were not exercised. The probe calls the same
  `skill_view` tool function that the agent's tool call resolves to.
- The "PHI detector" of the criterion is the US-3.1 `PhiDetector`. Its model step ran against a
  fake PHI model that answers the fixture's PHI. The real Qwen PHI model was not run (it is a
  `models`-marked test and would need downloaded weights). The regex validators
  (`claimcoach.redact.validators.find_regex_spans`) are the real ones.
- The spec delta (`openspec/changes/us-9-3-denial-triage-skill/specs/*/spec.md`) has the same two
  scenarios as SPECS.md. Its extra requirement text ("the playbook SHALL tell the agent to work
  from case IDs, codes, and payer names only and never to ask for documents in the chat") is
  covered by `test_us_9_3_playbook_keeps_the_phi_boundary`, which passed.
