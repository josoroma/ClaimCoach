# Proposal: US-9.3 Denial-Triage Skill

## Why

PRD §7: `skills/denial-triage/` is the agent's triage and explanation playbook, with no PHI.
US-1.1 left a placeholder `SKILL.md` that is not registered, so the agent cannot load it.

## What Changes

- `plugin/skills/denial-triage/SKILL.md`: the playbook (ground rules, the three tools, six triage
  steps, how to explain to the biller), with frontmatter (`name`, `description`, `version`,
  `metadata.hermes.tags`).
- `agent/skills.py`: `register_skills` reads the frontmatter and calls `ctx.register_skill(name,
  path, description, frontmatter)`; Hermes serves it as `claimcoach:denial-triage` in place.
- `register_agent` registers it; the Hermes probe reports registered skills.
- `make agent-skill` prints the skill as the agent sees it.

## Capabilities

### New Capabilities
- `denial-triage-skill`: the PHI-free playbook skill registered under the plugin namespace.

### Modified Capabilities
- None.

## Impact

- Hermes lists the skill in `<available_skills>` while the plugin is enabled.
