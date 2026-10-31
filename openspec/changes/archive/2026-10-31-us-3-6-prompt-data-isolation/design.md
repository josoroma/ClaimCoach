# Design: US-3.6 Uploaded Text Treated as Data in Prompts

## Context

Every model step (PHI detection, extraction, classification, explanation, drafting) sends
OpenAI-compatible chat messages to a local server. The risk is prompt injection from document
text, and the subtler risk of a developer formatting document text into an instruction string.

## Goals / Non-Goals

**Goals:** document text can only enter a prompt through one encoder, inside a delimited data
section; templates cannot carry per-call values; a test checks every pipeline template.

**Non-Goals:** detecting injection attempts in the data or filtering model output (the output of
each step is parsed into typed models by the step itself).

## Decisions

1. **Templates are constants; everything per-call is data.** `PromptTemplate` has only fixed
   `system` and `instructions` strings, created with `define_template()` at import time. Codes,
   payer names, and extracted fields are `DataItem`s too, so no runtime value is ever formatted
   into an instruction. *Alternative:* templates with `{placeholders}` — rejected, a placeholder
   is exactly how document text would leak into the instruction section.
2. **Random boundary per prompt** (`secrets.token_hex(12)`), redrawn if it occurs in any data
   item. A document cannot forge the closing marker. *Alternative:* fixed XML-like tags with
   escaping — rejected, escaping rules differ per model and a fixed tag is guessable.
3. **Data only in the user message.** The system message is template text plus the data rule.
   *Alternative:* a separate user message per item — rejected, one message keeps the
   instruction/data order explicit for small local models.
4. **A registry instead of a list of prompts in the test.** `registered_templates()` returns
   every template defined so far; the test imports `PIPELINE_MODULES` and checks each one, so a
   new prompt is covered as soon as its module is listed there.

5. **Enforced, not just conventional** (review finding). `build_prompt` refuses a template that is
   not the registered object of its name, and `BuiltPrompt` validates its own shape (system
   message exactly the registered system text plus the data rule; user message exactly the
   instructions followed only by data blocks closed with its boundary), so a prompt assembled
   by hand with document text in a fixed section cannot be constructed. The test discovers
   templates by importing every `claimcoach` module (`pkgutil.walk_packages`) instead of a
   hand-kept list.

## Risks / Trade-offs

- [A model still obeys text inside the data section] → the boundary stops structural escape, not
  model gullibility; each step parses output into typed models and US-3.1 redaction never depends
  on the model following instructions (regex validators run regardless).
- [A step builds messages by hand] → the chat client takes only a `BuiltPrompt`, and a
  `BuiltPrompt` fails validation unless every non-data byte is registered template text.
