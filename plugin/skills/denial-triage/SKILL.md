---
name: denial-triage
description: Triage a denied medical claim with ClaimCoach's PHI-free tools. Not registered yet; US-9.3 writes the playbook and registers it.
---

# Denial triage

Placeholder created by US-1.1 so the package layout matches PRD §7. US-9.3 replaces this body with
the triage and explanation playbook and registers it with `ctx.register_skill`.

Rules that already apply: use only case IDs, codes, and payer names (BR-3). Never ask the user to
paste claim documents into the chat; documents go into the ClaimCoach pane (BR-2).
