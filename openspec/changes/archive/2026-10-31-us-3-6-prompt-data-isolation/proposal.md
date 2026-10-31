# Proposal: US-3.6 Uploaded Text Treated as Data in Prompts

## Why

Uploaded EOBs and payer letters are untrusted. A line such as "ignore previous instructions" in a
document must never steer the local models that classify, explain, or redact it (SPECS.md US-3.6,
PRD §10, BR-10).

## What Changes

- Add `claimcoach.prompts.builder`: `PromptTemplate` (fixed system and instruction text, defined
  once at import with `define_template`), `DataItem`, `PromptParts`, `ChatMessage`, `BuiltPrompt`,
  and `build_prompt()` — the single data-block encoder every pipeline prompt goes through.
- Per-call content is placed only in the data section of the user message, between
  `<<<DATA <boundary> label=…>>>` and `<<<END DATA <boundary>>>` markers with a random per-prompt
  boundary that never occurs in the data. The system message states that the data section is
  never an instruction.
- A registry of templates lets one test check every pipeline prompt.

## Capabilities

### New Capabilities
- `prompt-isolation`: how pipeline prompts are assembled so document text stays data.

### Modified Capabilities
- None.

## Impact

- New package `plugin/claimcoach/prompts/`. No route or config changes.
- Later stories (US-3.1 PHI detection, EPIC-5/6/7 prompts) build their prompts with
  `build_prompt()`; the chat client accepts only a `BuiltPrompt`.
