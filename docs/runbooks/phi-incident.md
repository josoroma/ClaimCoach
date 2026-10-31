# Runbook: Suspected PHI exposure

Status: **skeleton, NEEDS CLARIFICATION** — SPECS.md US-1.5 Open Question: the incident-response
steps and notification obligations are not defined. PRD §10 states the HIPAA posture (the
practice is the covered entity) but not the procedure. Do not improvise notifications from this
page.

## Preconditions

- A suspected exposure: PHI in a log, an agent transcript, an event payload, or any outbound
  network call (BR-1, BR-3, BR-14).
- The practice's privacy officer and their contact path (to be supplied by the Product Manager).

## Steps

1. Contain: stop the worker (`make worker-stop`) and disable the Python half
   (`make plugin-disable && hermes gateway restart`).
2. Preserve: copy the affected log or transcript to encrypted storage; do not delete it.
3. Escalate: notify the practice's privacy officer. **Procedure and deadlines: pending Product
   Manager decision.**

## Verification

- The worker is stopped (`make worker-status` exits 1) and `claimcoach` is disabled
  (`hermes plugins list`).

## Rollback

- Re-enable only after the privacy officer closes the incident:
  [install-enable](install-enable.md) → Steps 3–5.
