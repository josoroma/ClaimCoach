# Runbook: the Hermes agent tools, the denial-triage skill, and /denial

Covers US-9.1 (`claimcoach_explain_code`, `claimcoach_payer_rules`: answers from the global
corpus), US-9.2 (`claimcoach_case_summary`: a case reduced to codes, the payer as its rule cards
name it, its status, and enums), US-9.3 (the `claimcoach:denial-triage` playbook skill), and
US-9.4 (the `/denial` slash command). Billers use them from the Hermes chat; these commands are
for operators checking what the agent gets. Every call runs the same guarded handler Hermes runs
(the result is redacted before it is printed, BR-3) and talks to the worker on `127.0.0.1` only.

The agent's transcript may leave the Mac when the Hermes chat model is a cloud model, so the tools
take and return only IDs, codes, payer names, and enums: no document text, claim number, date,
amount, or printed payer name. A case summary is recorded in the case's audit log as
`case_summarized`. `/denial` with no case ID answers a fixed guide; with one, the case's summary.

## Preconditions

- The plugin is installed and enabled (`make plugin-install`, see
  [install-enable](install-enable.md)); `make doctor` reports the plugin link.
- For `agent-call`, `agent-denial`, and the tools in the chat: the worker is running (`make
  start`, see [worker-start-stop-health](worker-start-stop-health.md)) with its PHI model
  (`phi_detection` in `make models-check`), because every result is redacted before it is shown.
- For the code and payer tools: the global corpus holds code entries and rule cards (`make
  corpus-list`; import with `make corpus-import FILE=<bundle>`, see
  [corpus-import-reindex-backup-restore](corpus-import-reindex-backup-restore.md)).
- For a case summary: the case exists in the active Hermes profile (`make case-show CASE=<id>`).

## Steps

1. See what the agent is offered (offline: tool names, parameter schemas, the skill, `/denial`):

   ```bash
   make agent-tools
   ```

2. Read the playbook skill as Hermes serves it (`skill_view("claimcoach:denial-triage")`):

   ```bash
   make agent-skill
   ```

3. Call a tool exactly as the agent does (ARGS is a JSON object; it reaches the tool through the
   environment, never the shell text):

   ```bash
   make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197"}'
   ```

   ```bash
   make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer": "Aetna"}'
   ```

   ```bash
   make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "<case id>"}'
   ```

4. Run `/denial`, without and with a case ID:

   ```bash
   make agent-denial
   ```

   ```bash
   make agent-denial CASE=<case id>
   ```

5. Load the plugin into the locally installed Hermes Agent (a throwaway `HERMES_HOME`, never
   `~/.hermes`) and check the tools, `skill_view`, and `/denial` through Hermes itself:

   ```bash
   make agent-probe
   ```

6. Restart the gateway after changing the tools, the skill, or the command (`make
   gateway-restart`); Hermes registers them when it loads the plugin.

## Verification

- `make agent-tools` lists `claimcoach_explain_code`, `claimcoach_payer_rules`, and
  `claimcoach_case_summary` (each with `"additionalProperties": false`; the case summary's only
  parameter is `case_id`), `skill: claimcoach:denial-triage`, and `command: /denial [case ID]`.
- `make agent-call` prints `"ok": true` and exits 0 for a known code, payer, or case. A code the
  corpus lacks prints `code_not_found`, an unknown payer `payer_not_found`, another profile's or
  a missing case `case_not_found`; for each the CLI exits 1 (so `make` stops with an error). A
  worker that is stopped prints `worker_unavailable`. None of these echoes the arguments.
- A case summary shows `status`, `stage`, `codes`, `payer` (`null` when no rule card matches),
  and the diagnosis enums, and no name, member ID, claim number, date, or amount. `make
  corpus-audit CASE=<case id>` shows a `case_summarized` entry for every summary.
- `make agent-denial` prints the guide; with a case ID it prints the case's status, payer, codes,
  and next step.
- `make agent-probe` passes (each test skips when Hermes is not installed).

## Rollback

- The tools, skill, and command are registered only while the plugin is enabled: `make
  plugin-disable` then `make gateway-restart` removes them from the agent (the pane and the worker
  keep working).
- The tools never change stored data; a case summary only appends an audit entry, which is kept
  by design (the audit log is append-only).
- To return to a previous version of the playbook, restore `plugin/skills/denial-triage/SKILL.md`
  from version control and restart the gateway.
