# Fictional ClaimCoach video inputs

All identities, claims, payer rules, and dates are synthetic. Nothing here is a
patient record, an authentic payer policy, or a claim to send.

- `northstar-demo.835`: a single CO-197 denial for $250. It has no RARC so the
  authorization teaching point stays unambiguous. The X12 usage indicator is `T`.
- `northstar-demo-rules.json`: two uniquely named fictional payer rule cards and
  one uniquely named appeal template. It deliberately has no global CARC or
  GROUP entries, so importing it does not replace existing code definitions.
- `denial-notice.txt`: human-readable companion for the video; use the 835 for
  the primary intake to demonstrate the deterministic parser.
- `expected-reading.json`: production parser result, generated locally for
  artifact verification. It is not an AI diagnosis or a successful live run.

The fictional card's calculation is 2026-10-15 + 180 calendar days = 2027-04-13.
Use the exact source and verification label on screen so the example cannot be
mistaken for a current insurer rule. Do not record a successful outcome: the
sample ends at a draft for review.

For an **empty isolated demo corpus**, `isolated-demo-corpus.json` combines the
fictional rules, the unique letter template, a default appeal template for the
pane, and two reference code entries verified against X12 on 2026-11-02.
Do not import this combined bundle into an existing corpus without reviewing
which code/template keys it replaces. `demo-code-reference.json` holds only the
two reference entries, with source links.
