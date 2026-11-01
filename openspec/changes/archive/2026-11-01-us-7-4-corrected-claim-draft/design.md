# Design: US-7.4 corrected claim draft

## Context

A diagnosed case holds the extraction (payer, claim ID, amounts, CARC/RARC/group codes, and per
line the procedure code, service date, and amounts; US-5.2) and its diagnosis (the denial reason,
one of eleven families, and the codes it read; US-6.1). The appeal draft (US-7.1) is a `draft`
job on the case's one job registry, stored as a sealed case item, stale once the extraction
digest or the diagnosis time changes, and exported as PDF or DOCX by US-7.2. A case's sources
are pdf, image, edi_835, and text: the ERA and the denial letter, never the original 837 or
CMS-1500. So the case holds no ICD-10 code, modifier, unit count, NPI, place of service, or
member ID.

SPECS.md US-7.4 asked what a corrected-claim draft is and which denials route to it. The PM
approved the recorded defaults on 2026-11-01; this design is those defaults made precise.

## Goals / Non-Goals

Goals: recommend the remedy for every diagnosed case with fixed rules; on request, draft a list
of the changes a corrected claim needs, traceable to the case's documents and codes, labeled for
human review, stale when the case changes, and exportable.

Non-Goals: a claim form or an 837 (Non-goals §5: no clearinghouse, no submitting); proposing a
CPT, HCPCS, ICD-10, or modifier value (Non-goals §5: no coding); editing the list in the pane
(the biller makes the changes in their billing system); an agent tool for the draft; reading the
original CMS-1500 (a later v1.1 source kind).

## Decisions

1. **A list of changes, not a claim.** `CorrectedClaimDraft` holds the label, the original claim
   ID (absent when unreadable), the claim frequency code as an instruction, at least one
   `ClaimCorrection` (at most 40), the payer's rule cards it was drafted with, the extraction
   digest, and the diagnosis and draft times. A `ClaimCorrection` holds a line number (1-based;
   none for the claim), a `CorrectableField` (`procedure_code`, `modifier`, `diagnosis_code`,
   `diagnosis_pointer`, `units`, `service_date`, `place_of_service`, `member_id`,
   `patient_demographics`, `other_insurance`, `claim_data`), the current value, the codes behind
   it, and the model's `action` and `why`. Rejected: claim-form fields and an 837 snippet (the
   data is not in the case, and both cross Non-goals §5).
2. **Current values come only from the extraction.** Only a line's `procedure_code` and
   `service_date` can have one, and only when that field was read or confirmed; every other
   field, and any unread value, is absent, shown as "not in your documents". The value is
   copied by code, never by the model, and `ClaimCorrection` refuses a current value on a field
   the extraction cannot hold.
3. **The changes are planned by fixed rules.** Each code maps to the fields it points at:
   CARC 4 → modifier, procedure code; 5 → procedure code, place of service; 6 and 7 → procedure
   code, patient demographics; 11 → diagnosis pointer, diagnosis code; 31 → member ID, patient
   demographics; 97 and 234 → modifier; 236 → modifier, procedure code; 181 → procedure code,
   service date; 182 → modifier, service date; 22 and 23 → other insurance; RARC M51 → procedure
   code; M53 → units; M76 → diagnosis code; M77 → place of service; MA61 and N382 → member ID;
   MA130 → claim data. A code on a line points at that line; a claim-level code points at the
   claim for claim fields and at every line for line fields. Changes to one (line, field) merge
   their codes; the draft lists the first 40, in line order, and records how many more there
   are (`omitted`), which the pane and the export state so the biller checks every line. When no code maps, one claim-level
   `claim_data` change cites the case's codes. Rejected: letting the model choose fields (it
   would pick fields the documents cannot support).
4. **The model writes only the words.** The `correction_draft` template sends the letter facts,
   the diagnosis, the planned changes (index, line, field, current value or "not in your
   documents", codes), and the payer's rule cards to the `drafting` role, and asks for
   `{"corrections": [{"index", "action", "why"}]}`. The parser requires every index exactly
   once and non-blank text (500 characters each, clipped), and refuses the whole reply when an
   action or why names any modifier value (next to "modifier" or "mod" in either order and with
   any separator, after a procedure code as `99213-25`, or a letter modifier such as `XS`), or a
   code-shaped value (a CPT or HCPCS code, an ICD-10 code with or without its dot) that the
   case's procedure codes, CARCs, RARCs, claim ID, and amounts do not hold (`X12` and `P2P` are
   words, not codes). A refused
   reply ends the job `correction_failed` and stores nothing. Rejected: trusting the prompt
   alone (a model asked for a bundling fix writes "append modifier 59"); replacing refused text
   with fixed wording (it would hide that the model's text was unusable).
5. **A table decides the remedy, not the model.** `recommended_remedy` is pure: a payer's
   `corrected_claims` rule card naming the denial reason in its `remedies` wins (`basis:
   rule_card`); otherwise the reason decides (`basis: table`): coding_error → corrected claim;
   bundling, coordination_of_benefits → either; medical_necessity, prior_authorization,
   timely_filing, non_covered_service → appeal; duplicate_claim, other → none (verify first).
   Two reasons are split by codes (`basis: codes`): eligibility is a corrected claim with CARC
   31 and none with CARC 27; missing_information is a corrected claim with a claim-data RARC
   (M51, M53, M76, M77, MA61, N382, MA130) and an appeal with an attachment code (CARC 252, 226,
   227; RARC M127, N29, N706). Neither or both is either. The advice names the codes that
   decided it and the card. Rejected: a field on `Diagnosis` (it would change US-6.1's stored
   type and run a model to route).
6. **The remedy is computed on read.** Like the appeal deadline, `Case.remedy` is recomputed
   from the current diagnosis, extraction, and global rule cards on every read, so a newly
   imported card shows at once; a stale or missing diagnosis has no remedy. It is a
   recommendation: the pane offers both drafts, and the biller can ask for either.
7. **The frequency code is fixed by rules.** RARC MA130 (unprocessable, no appeal rights) is 1,
   a new claim; anything else is 7, a replacement; a payer's `corrected_claims` card may set 1,
   7, or 8 (void). The pane and the export say what each means. Rejected: 7 and 8 only (an
   unprocessable claim is resubmitted as new).
8. **The same pipeline as the appeal draft.** A fourth job kind `correct` on the one registry
   (one job per case, so a correction never reads a diagnosis being rewritten), progress
   `drafting` then `done`, refusals before the job starts (`case_closed`, `not_diagnosed`), the
   `correction` case item audited `correction_drafted`, `correction_stale` by the extraction
   digest and diagnosis time, pane → `plugin_api.py` → worker (BR-2). Drafting again replaces
   it. No template is needed.
9. **Export through US-7.2.** The stored correction renders as text (a heading with the label,
   the claim ID and frequency code, "make these changes in your billing system", one numbered
   item per change with its codes) through US-7.2's PDF and DOCX writers, with "Draft for human
   review" on every page and as the first paragraph; the file is `corrected-claim-draft-<case
   id>.<pdf|docx>` in the same 15-minute exports folder; the export is audited
   `correction_exported`. A closed case still exports.
10. **A sixth rule-card topic.** `corrected_claims` cards carry `remedies` (denial reason →
    remedy) and `frequency_code`; both fields are allowed only on that topic, as US-6.2 and
    US-6.3 fields are. A payer can now have six cards, so `Diagnosis.rule_cards` and
    `AppealDraft.rule_cards` hold six; the agent's payer-rule card type accepts the topic.
11. **No agent tool.** The draft holds claim values, so no agent tool reads it and the redacted
    case summary (US-9.2) is unchanged.

## Risks / Trade-offs

- [The table is guidance, payers differ] → a payer's `corrected_claims` card overrides it; the
  pane says the recommendation's basis and offers both drafts.
- [A code-shaped false positive refuses a good reply] → the allowed set includes every code and
  amount in the case; the prompt forbids other codes; the biller can draft again or appeal.
- [Without the original claim, most current values are absent] → each says "not in your
  documents"; v1.1 may add the CMS-1500 as a source.
- [A claim of many lines fans a claim-level code out] → 40 changes are listed in line order and
  the rest are counted (`omitted`), so the biller is told to check every line.
