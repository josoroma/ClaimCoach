# ClaimCoach demonstration quality review

This is an integration demonstration with fictional training data, recorded on
2026-11-02 in the user's America/Costa_Rica timezone. It does not establish a
production release gate, billing accuracy, appeal success, or regulatory status.

## Verified fixture and embedding behavior

- The production X12 parser read the fictional payer, single claim, dates,
  $250 charge, $0 payment, and CO-197 adjustment. No additional claims were found.
- The production bundle validator accepted all six isolated-demo corpus items.
- Real local Qwen3-Embedding-8B weights produced 4096-dimensional unit vectors.
  Identical text was consistent; the related sentence scored higher than the
  unrelated sentence. See `runtime/embedding-validation.json`.
- `local-routing.json` audits 21 configured main, auxiliary, and delegation
  routes. They use loopback endpoints and the global fallback lists are empty.
  This is a configuration check, not a packet capture or zero-egress audit.

## Actual model issues requiring human review

The unchanged initial model output is retained at
`outputs/case-original-model-result.json`.

1. The diagnosis says the payer may accept authorization completed after the
   service. The fictional source cards contain no retroactive-authorization
   rule, so this statement is unsupported.
2. The root-cause text says the provider failed to obtain or submit authorization
   before service. CO-197 reports the payer's reason; this sample does not prove
   what the provider did or whether authorization exists.
3. The initial appeal draft says supporting documents are attached even though
   the demo contains only its source remittance. Enclosures must be marked
   pending and checked by a reviewer.
4. The initial draft copies a template instruction into the letter. That text
   must be replaced with a clear placeholder or reviewer action.
5. The model's “medium” appeal-likelihood label is an uncalibrated result for one
   sample. It is not an outcome probability or an accuracy result.

These findings explain why the demonstration shows editing before export and
requires human review. The assistant acting as the demo operator made the
recorded edits; no clinician or biller approval is claimed. The initial raw
output and edited draft remain distinct. Neither is ready to submit.

## Runtime limits observed

The primary agent observed a first drafting failure caused by memory pressure
in the MTPLX server. Drafting succeeded after the unused embedding model was
unloaded and the request was retried. This run does not prove that concurrent
models fit reliably or that the standard model registry works unchanged.

The demo uses the installed Bonsai model for text roles whose default Qwen
weights are absent. Its model bridge and embedding adapter are documented under
`runtime/`. The default vision/extraction models were not exercised: the
recorded input uses the deterministic 835 parser.

## Agent evidence

`agent-loop.json` and `agent-responses.md` contain the canonical Hermes session's
actual model-selected calls and returned tool data. `command-receipt.json`, when
present, records the separately executed `/denial` command. A slash-command
summary alone is not evidence of the agent's tool loop.

Check the receipt's completion state before claiming the loop finished. The
agent must not receive full claim documents in its prompt; this run starts with
only the synthetic case ID, code, and payer name.

## Final recorded results

The completed canonical Hermes loop called `skill_view`, discovered plugin
tools, and invoked all three ClaimCoach handlers. Each returned `ok: true`.
The agent's final answer warned against inventing authorization evidence,
labeled the payer policy fictional, and kept review/export with the biller.
It unnecessarily suggested confirming highlighted fields despite the summary
reporting zero fields requiring confirmation.

The operator-edited draft was saved through ClaimCoach, then exported by the
actual worker as PDF and DOCX. Both final files render to one clean page and
match the edited text. The initial PDF orphaned its signature on page two;
compacting the signature placeholders in the saved draft fixed the pagination.
`outputs/export-receipt.json` records hashes, content checks, and visual review.
No appeal outcome was recorded and nothing was submitted.

## Desktop agent loop and recovery

The separately recorded Desktop session is
`local-c35cd5911c689212e03949e6103e19d5a6b24fadf62dcf40d6fefb645eb2ecc0`.
Its canonical messages are preserved in `desktop-agent-loop.json` and
`desktop-agent-responses.md`; the earlier successful CLI receipt is unchanged.

The model's first payer-rule call put `arguments` on the outer `tool_call`
object instead of inside its `calls[0]` entry. Hermes validation rejected the
missing `payer` argument and explicitly reported that the plugin was not
invoked. The model then corrected the nesting and called the tool successfully,
receiving two fictional payer cards. All three ClaimCoach handlers ultimately
returned `ok: true`, and the agent completed its answer. The visible “1 failed”
indicator records that recovered argument-validation error, not an unreported
payer-rule result or an error-free run.
