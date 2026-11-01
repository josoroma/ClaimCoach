# Design: US-9.3 denial-triage skill

## Context

Hermes v0.22.5 `PluginContext.register_skill(name, path, description="", frontmatter=None)`
registers a read-only skill served as `<plugin>:<name>` by `skill_view()`; the name may not
contain `:` and the file must exist. The agent half registers in `register(ctx)`.

## Goals / Non-Goals

Goals: one playbook the agent loads by name, written so following it never needs PHI.

Non-Goals: per-payer playbooks (the rule cards are the per-payer source); skill files beyond
`SKILL.md`.

## Decisions

1. **The file is the single source of truth.** `register_skills` parses the `SKILL.md`
   frontmatter and registers with its `name` and `description`; a test pins the name to
   `denial-triage`. Rejected: a description constant in Python (it would drift from the file).
2. **PHI-free by content and by test.** The playbook speaks of case IDs, codes, and payer names,
   tells the agent never to ask for documents in the chat, and contains no example patient data;
   a test runs the US-3.1 detector (fake PHI model, real regex validators) over every skill file.
   Rejected: example letters with fictional names (the detector would rightly flag them).
3. **Real Hermes check.** The US-1.1 probe reports `_plugin_skills`, and a `hermes`-marked test
   calls the real `skill_view("claimcoach:denial-triage")`; both skip when Hermes is absent.

## Risks / Trade-offs

- [A malformed frontmatter would stop `register(ctx)`] → it is a packaged file, parsed in tests on
  every `make check`.
