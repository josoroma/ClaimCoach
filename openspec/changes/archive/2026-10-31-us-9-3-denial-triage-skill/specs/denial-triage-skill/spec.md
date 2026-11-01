# Spec Delta

## Purpose

Defines the denial-triage playbook skill the Hermes agent loads from the ClaimCoach plugin.

## ADDED Requirements

### Requirement: Skill is registered under the plugin namespace
The agent half SHALL register `plugin/skills/denial-triage/SKILL.md` with `ctx.register_skill`
under the bare name `denial-triage`, using the file's frontmatter, so that Hermes serves it as
`claimcoach:denial-triage`.

#### Scenario: Skill is registered under the plugin namespace
- **WHEN** the plugin is enabled and the agent loads skill_view("claimcoach:denial-triage")
- **THEN** the skill content is returned

### Requirement: Skill content contains no PHI
Every file of the skill SHALL contain no PHI span, and the playbook SHALL tell the agent to work
from case IDs, codes, and payer names only and never to ask for documents in the chat.

#### Scenario: Skill content contains no PHI
- **WHEN** the PHI detector scans the skill files
- **THEN** no PHI span is found
