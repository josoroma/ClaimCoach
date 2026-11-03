# ClaimCoach video product evidence

Prepared 2026-11-02. This file separates implemented behavior from what the current recording actually proves. Use the live-run evidence and screenshots to update the latter before the final edit.

## Demo concept

An entry-level biller turns a fictional denied claim into a reviewed next step, inside Hermes Desktop. The visual reveal is the boundary: patient documents go to the ClaimCoach pane and local models; the agent uses constrained case summaries and reference tools. The human reviews and exports the draft.

This is a product demonstration prepared for a Y Combinator audience. It does not imply YC admission, endorsement, customers, recovered revenue, or validated clinical/billing accuracy.

## What the repository implements

| On-screen step | Implemented behavior | Source |
| --- | --- | --- |
| Enable plugin | Hermes Python plugin plus desktop pane must both be enabled | `docs/runbooks/install-enable.md`, `plugin/plugin.yaml` |
| Set local models | Worker uses `MODELS_HOME`, default `~/Models`; model roles start on loopback | `README-DEV.md`, `plugin/claimcoach/models/models.default.yaml` |
| New case / paste 835 | One case holds encrypted source documents; 835 is parsed deterministically | `plugin/claimcoach/cases/service.py`, `plugin/claimcoach/pipeline/edi835.py` |
| Confirm fields | Unreadable fields can be confirmed; confirmations survive re-extraction | `plugin/claimcoach/cases/extraction.py` |
| Diagnose | Local inference classifies denial, explains it, and selects documents from exact payer cards | `plugin/claimcoach/pipeline/diagnose.py`, `plugin/claimcoach/pipeline/explain.py` |
| Appeal deadline | Denial date + the exact card's calendar-day limit; missing evidence produces unknown | `docs/runbooks/case-diagnosis.md`, `tests/test_us_6_3_deadline.py` |
| Draft / review / export | Appeal or corrected-claim draft; save human edits, export PDF or DOCX | `docs/runbooks/appeal-drafting.md` |
| Hermes loop | Agent invokes constrained tools, observes results, and provides next steps using a skill | `plugin/skills/denial-triage/SKILL.md`, `plugin/claimcoach/agent/` |
| `/denial` | No argument gives a guide; case ID gives a safe summary | `plugin/claimcoach/agent/commands.py` |
| Human decision | There is no send, fax, email, or submit operation | `tests/test_us_7_3_no_send_submit.py` |

Agent tools: `claimcoach_case_summary`, `claimcoach_explain_code`, `claimcoach_payer_rules`.
Skill: `claimcoach:denial-triage`. Command: `/denial [case ID]`.

Do not portray multiple independent agent personas as an existing product feature. The plugin exposes specialist tools and a triage skill to the Hermes agent loop. This project's video-production agents are distinct from the product's runtime.

## Synthetic case

All sample identities and payer policies are fictional. Use the persistent label **Fictional training sample** during case footage.

- Payer: Northstar Demo Health.
- Case reference: DEMO-CLAIM-001 (the runtime assigns a separate `case_<hex>` identifier).
- Service: 99213, dated 2026-09-01.
- Denial notice: 2026-10-15.
- Billed: $250. Paid: $0. Adjustment: CO-197, $250.
- Fictional payer limit: 180 calendar days → 2027-04-13.
- Fictional checklist: denial notice; authorization record if available; supporting service documentation.
- Authorization is **not established**. The draft must not assert that it exists.
- End at review/export. Do not manufacture a successful appeal outcome.

`demo-inputs/expected-reading.json` was produced by the real application parser, and `northstar-demo-rules.json` passed the production bundle validator. These are artifact validation, not proof of model diagnosis or desktop execution.

## Operator sequence

Use the root agent's isolated demo `HERMES_HOME` and model configuration. Commands below require the real worker and model services to be running.

```sh
make corpus-import FILE=docs/video-artifacts/demo-inputs/northstar-demo-rules.json
make case-new
make case-paste CASE=<assigned-case-id> FILE=docs/video-artifacts/demo-inputs/northstar-demo.835
make case-process CASE=<assigned-case-id>
make case-show CASE=<assigned-case-id>
make case-diagnose CASE=<assigned-case-id>
make case-draft CASE=<assigned-case-id> TEMPLATE=appeal-video-demo
make case-export CASE=<assigned-case-id> FORMAT=pdf TO=docs/video-artifacts/outputs
make agent-denial CASE=<assigned-case-id>
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id":"<assigned-case-id>"}'
make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer":"Northstar Demo Health"}'
```

The primary bundle has no global code entries, avoiding changes to a user's real reference corpus. A separate `demo-code-reference.json` can populate CO and 197 in an empty isolated demo corpus. The unique template is requested explicitly with `TEMPLATE=appeal-video-demo`; the pane's default draft action searches `appeal-prior-authorization` then `appeal`, so a default template must also be imported if recording that action through the pane.

Useful live Hermes prompt, substituting the actual case ID:

> Use the claimcoach:denial-triage skill for case <assigned-case-id>. Read its summary, explain CO-197 with the code tool, and check Northstar Demo Health's rule cards. Give me the next actions in the ClaimCoach pane. Treat this as fictional training data and do not invent missing authorization evidence.

## Suggested screen order (about 140 seconds)

| Segment | Focus | Evidence to show |
| --- | --- | --- |
| 1 | The biller's job | ClaimCoach mark and one-line promise: understand the denial, prepare the next step |
| 2 | Local setup | Actual Hermes model setting and ClaimCoach enable state |
| 3 | Start a case | Real pane, New case, fictional 835 input |
| 4 | Review extraction | Payer, dates, amount and CO-197; confirm only if needed |
| 5 | Read the explanation | Actual model output, missing evidence and fictional policy source |
| 6 | Check the deadline | Card-sourced 180-day example and 2027-04-13 date |
| 7 | Ask the agent | `/denial`, skill name and actual safe tool calls |
| 8 | Understand the loop | Ask → skill → local tool → observe result → next action |
| 9 | Review the draft | Real generated draft, human-review label, edit and export |
| 10 | Close | Local consumer hardware, biller in control, no fabricated business metrics |

## Claims to keep bounded

The existing README says acceptance tests used stand-in models and live Hermes/model validation had not run. A successful recording can establish the particular run only; it cannot establish production release gates, a 98% PHI score, 85% classification accuracy, 70% draft quality, ten-minute median workflow, HIPAA certification, or appeal success. Those values are targets, not demonstrated results.

The default architecture uses models between 8B and 27B. Describe them as local open-weight models; “small model” is relative and should not imply that every consumer laptop can run every configured role. State the actual Mac and model configuration used for this demo in the artifact README. If the demo maps missing text roles to installed Bonsai, identify that as the demo configuration.
