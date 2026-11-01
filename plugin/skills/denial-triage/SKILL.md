---
name: denial-triage
description: Triage a denied medical claim and explain it to a biller with ClaimCoach's PHI-free tools (case IDs, codes, and payer names only).
version: 1.0.0
metadata:
  hermes:
    tags: [medical-billing, denials, claimcoach]
    related_skills: []
---

# Denial triage

Use this playbook when a biller asks why a claim was denied, what a denial code means, what a
payer requires, or what to do next on a ClaimCoach case.

## Ground rules

- Work only with case IDs, codes, and payer names. Never ask for, repeat, or guess a patient's
  name, date of birth, member ID, address, phone number, or any other patient detail.
- Never ask the biller to paste an EOB, an 835, a denial letter, or medical records into the chat.
  Documents go into the ClaimCoach pane, which keeps them on this Mac.
- Answer from the ClaimCoach tools. If a tool returns an error, say what the error says and what
  the biller can do; do not fill the gap with a guess about the payer's rules.
- ClaimCoach never sends, submits, faxes, or files anything. Appeals are drafts for human review.

## Tools

| Tool | Ask it for | Argument |
| --- | --- | --- |
| `claimcoach_case_summary` | A case's status, stage, codes, payer, denial reason, appeal likelihood | `case_id` |
| `claimcoach_explain_code` | What a group, reason (CARC), or remark (RARC) code means | `code`, e.g. `CO-197`, `N286` |
| `claimcoach_payer_rules` | The payer's filing limit, appeal levels, required documents | `payer` |

## Triage steps

1. **Find the case.** If the biller names a case ID, call `claimcoach_case_summary`. Without one,
   ask for the case ID shown in the ClaimCoach pane, or suggest `/denial` to get started.
2. **Read the codes.** For each code in the summary, call `claimcoach_explain_code`. The group
   code says who is responsible: `CO` contractual obligation (the provider may not bill the
   patient), `PR` patient responsibility, `OA` other adjustment, `PI` payer initiated, `CR`
   correction or reversal. Remark codes (`N…`, `M…`, `MA…`) add the detail.
3. **Name the denial family.** Use the summary's denial reason when the case was diagnosed. If the
   diagnosis is out of date, say so and suggest diagnosing again in the pane. Common families:
   eligibility, prior authorization, medical necessity, coding error, missing information,
   duplicate claim, timely filing, non-covered service, bundling, coordination of benefits.
4. **Check the payer's rules.** Call `claimcoach_payer_rules` with the summary's payer. Quote the
   appeal limit and the required documents from the cards. Flag a card marked `stale`: the
   manager should verify it before the biller relies on it.
5. **Decide the path.**
   - A front-end error (coding, missing information, eligibility fixed after the fact): fix the
     claim and send a corrected claim through the usual channel.
   - A clinical or authorization denial with support on file: appeal, with the payer's required
     documents.
   - A duplicate, or a write-off the contract requires: no appeal; explain why.
6. **Say what is next in the pane.** Confirm highlighted fields, diagnose, draft the appeal, then
   review and export the draft. Remind the biller that the appeal deadline in the pane is
   computed from the payer's card and the denial date.

## Explaining to the biller

- Lead with one sentence: what the payer decided and why, in plain words.
- Then the fix: the steps and the documents, in the order the payer's card lists them.
- Then the risk: the appeal likelihood and anything that is unknown (no rule card, an unread
  denial date, a stale card).
- Keep codes as codes (`CO-197`); do not invent descriptions that the tools did not return.
