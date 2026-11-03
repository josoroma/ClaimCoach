# Actual local Hermes tool loop

Fictional training case. Recorded tool calls and outputs from the canonical Hermes session.

## Request

Use the ClaimCoach plugin to triage fictional training case case_ef4492f90f971935. First call skill_view for claimcoach:denial-triage. Then call claimcoach_case_summary for that case. Use claimcoach_explain_code for CO-197 and claimcoach_payer_rules for Northstar Demo Health. Read the actual tool outputs and give a concise next-step checklist for the ClaimCoach pane. Clearly label the payer policy as fictional. Do not invent missing authorization evidence. Do not use any other tools or alter the case. There is no need to send or submit anything.

Tool call: `skill_view`

```json
{"name":"claimcoach:denial-triage"}
```

## Tool response: skill_view

```text
{"success": true, "name": "claimcoach:denial-triage", "content": "[Bundle context: This skill is part of the 'claimcoach' plugin.]\n\n---\nname: denial-triage\ndescription: Triage a denied medical claim and explain it to a biller with ClaimCoach's PHI-free tools (case IDs, codes, and payer names only).\nversion: 1.0.0\nmetadata:\n  hermes:\n    tags: [medical-billing, denials, claimcoach]\n    related_skills: []\n---\n\n# Denial triage\n\nUse this playbook when a biller asks why a claim was denied, what a denial code means, what a\npayer requires, or what to do next on a ClaimCoach case.\n\n## Ground rules\n\n- Work only with case IDs, codes, and payer names. Never ask for, repeat, or guess a patient's\n  name, date of birth, member ID, address, phone number, or any other patient detail.\n- Never ask the biller to paste an EOB, an 835, a denial letter, or medical records into the chat.\n  Documents go into the ClaimCoach pane, which keeps them on this Mac.\n- Answer from the ClaimCoach tools. If a tool returns an error, say what the error says and what\n  the biller can do; do not fill the gap with a guess about the payer's rules.\n- ClaimCoach never sends, submits, faxes, or files anything. Appeals are drafts for human review.\n\n## Tools\n\n| Tool | Ask it for | Argument |\n| --- | --- | --- |\n| `claimcoach_case_summary` | A case's status, stage, codes, payer, denial reason, appeal likelihood | `case_id` |\n| `claimcoach_explain_code` | What a group, reason (CARC), or remark (RARC) code means | `code`, e.g. `CO-197`, `N286` |\n| `claimcoach_payer_rules` | The payer's filing limit, appeal levels, required documents | `payer` |\n\n## Triage steps\n\n1. **Find the case.** If the biller names a case ID, call `claimcoach_case_summary`. Without one,\n   ask for the case ID shown in the ClaimCoach pane, or suggest `/denial` to get started.\n2. **Read the codes.** For each code in the summary, call `claimcoach_explain_code`. The group\n   code says who is responsible: `CO` contractual obligation (the provider may not bill the\n   patient), `PR` patient responsibility, `OA` other adjustment, `PI` payer initiated, `CR`\n   correction or reversal. Remark codes (`N…`, `M…`, `MA…`) add the detail.\n3. **Name the denial family.** Use the summary's denial reason when the case was diagnosed. If the\n   diagnosis is out of date, say so and suggest diagnosing again in the pane. Common families:\n   eligibility, prior authorization, medical necessity, coding error, missing information,\n   duplicate claim, timely filing, non-covered service, bundling, coordination of benefits.\n4. **Check the payer's rules.** Call `claimcoach_payer_rules` with the summary's payer. Quote the\n   appeal limit and the required documents from the cards. Flag a card marked `stale`: the\n   manager should verify it before the biller relies on it.\n5. **Decide the path.**\n   - A front-end error (coding, missing information, eligibility fixed after the fact): fix the\n     claim and send a corrected claim through the usual channel.\n   - A clinical or authorization denial with support on file: appeal, with the payer's required\n     documents.\n   - A duplicate, or a write-off the contract requires: no appeal; explain why.\n6. **Say what is next in the pane.** Confirm highlighted fields, diagnose, draft the appeal, then\n   review and export the draft. Remind the biller that the appeal deadline in the pane is\n   computed from the payer's card and the denial date.\n\n## Explaining to the biller\n\n- Lead with one sentence: what the payer decided and why, in plain words.\n- Then the fix: the steps and the documents, in the order the payer's card lists them.\n- Then the risk: the appeal likelihood and anything that is unknown (no rule card, an unread\n  denial date, a stale card).\n- Keep codes as codes (`CO-197`); do not invent descriptions that the tools did not return.\n", "description": "Triage a denied medical claim and explain it to a biller with ClaimCoach's PHI-free tools (case IDs, codes, and payer names only).", "linked_files": null, "readiness_status": "available", "skill_dir": "/Users/josoroma/sites/ycombinator/claimcoach/plugin/skills/denial-triage"}
```

Tool call: `tool_search`

```json
{"queries":["ClaimCoach case summary case","explain denial code","payer rules filing limits"]}
```

## Tool response: tool_search

```text
{"queries": ["ClaimCoach case summary case", "explain denial code", "payer rules filing limits"], "total_available": 3, "results": [{"query": "ClaimCoach case summary case", "matches": ["claimcoach_case_summary"]}, {"query": "explain denial code", "matches": ["claimcoach_explain_code"]}, {"query": "payer rules filing limits", "matches": ["claimcoach_payer_rules"]}], "tools": {"claimcoach_case_summary": {"source": "plugin", "source_name": "claimcoach", "description": "Return a redacted summary of a ClaimCoach case by case ID: its status, stage, codes, payer (as the rule cards name it), denial reason, and appeal likelihood. No case text or PHI.", "required": ["case_id"]}, "claimcoach_explain_code": {"source": "plugin", "source_name": "claimcoach", "description": "Explain a denial code (CARC/RARC/group, e.g. CO-197) from the ClaimCoach global corpus.", "required": ["code"]}, "claimcoach_payer_rules": {"source": "plugin", "source_name": "claimcoach", "description": "Return the payer rule cards (filing limits, appeal levels, required documents) from the ClaimCoach global corpus.", "required": ["payer"]}}}
```

Tool call: `tool_call`

```json
{"calls":[{"name":"claimcoach_case_summary","arguments":{"case_id":"case_ef4492f90f971935"}}]}
```

## Tool response: claimcoach_case_summary

```text
{"ok": true, "case_id": "case_ef4492f90f971935", "status": "open", "stage": "drafted", "outcome": null, "payer": "Northstar Demo Health", "codes": ["CO-197"], "denial_reason": "prior_authorization", "appeal_likelihood": "medium", "diagnosis_stale": false, "deadline": "computed", "documents": 1, "needs_confirmation": 0}
```

Tool call: `tool_call`

```json
{"calls": [{"name": "claimcoach_explain_code", "arguments": {"code": "CO-197"}}]}
```

Tool call: `tool_call`

```json
{"calls": [{"name": "claimcoach_payer_rules", "arguments": {"payer": "Northstar Demo Health"}}]}
```

## Tool response: claimcoach_explain_code

```text
{"ok": true, "code": "CO-197", "entries": [{"code_set": "GROUP", "code": "CO", "title": "Contractual obligation", "explanation": "Contractual obligation.", "truncated": false, "source": "X12 Claim Adjustment Group Codes: https://x12.org/codes/claim-adjustment-group-codes", "verified_on": "2026-11-02", "stale": false}, {"code_set": "CARC", "code": "197", "title": "Authorization-related denial", "explanation": "Precertification/authorization/notification/pre-treatment absent.", "truncated": false, "source": "X12 CARC 197: https://x12.org/codes/claim-adjustment-reason-codes", "verified_on": "2026-11-02", "stale": false}]}
```

## Tool response: claimcoach_payer_rules

```text
{"ok": true, "payer": "Northstar Demo Health", "cards": [{"payer": "Northstar Demo Health", "topic": "appeal_levels", "title": "Demo first-level appeal", "body": "FICTIONAL DEMO POLICY. First-level appeals may be prepared within 180 calendar days of the denial notice. This sample is for product demonstration only.", "truncated": false, "required_documents": [], "appeal_limit_days": 180, "source": "Fictional ClaimCoach video fixture; not an insurer policy", "verified_on": "2026-11-02", "stale": false}, {"payer": "Northstar Demo Health", "topic": "required_docs", "title": "Demo authorization-denial documentation", "body": "FICTIONAL DEMO POLICY. An authorization-denial appeal packet includes the denial notice, evidence of authorization if available, and the relevant service documentation. Missing evidence must be requested; never invent it.", "truncated": false, "required_documents": ["Copy of the denial notice", "Authorization record, if available", "Documentation supporting the billed service"], "appeal_limit_days": null, "source": "Fictional ClaimCoach video fixture; not an insurer policy", "verified_on": "2026-11-02", "stale": false}]}
```

## Agent answer

All tools returned data for case case_ef4492f90f971935.

Case summary (redacted):
- Status: open, stage: drafted, outcome: none yet
- Payer: Northstar Demo Health
- Codes: CO-197
- Denial reason: prior_authorization
- Appeal likelihood: medium
- Diagnosis stale: false
- Documents on file: 1
- Needs confirmation: 0

Code meaning:
- Group CO: contractual obligation.
- CARC 197: authorization-related denial (precertification/authorization/notification/pre-treatment absent).

Payer policy cards: labeled FICTIONAL DEMO POLICY; source states "Fictional ClaimCoach video fixture; not an insurer policy."

ClaimCoach pane next-step checklist:
1. Confirm the highlighted fields and the denial notice in the pane.
2. Verify the single attached document against the required appeal packet: denial notice, authorization record if available, and service documentation.
3. Do not invent or assume authorization evidence; if the authorization record is missing, request it from the provider or client first.
4. Draft the appeal using only the documentation that actually exists.
5. Remind the biller the 180-day first-level appeal window is a fictional demonstration value, not a real insurer deadline.
6. Review and export the appeal draft for human review; ClaimCoach does not send or submit it.
