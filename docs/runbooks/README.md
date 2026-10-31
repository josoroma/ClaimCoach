# Runbooks

ES-6: every runbook has **Preconditions, Steps (copy-paste commands), Verification, Rollback**.
`test_us_1_5_runbooks_have_sections` enforces it.

| Runbook | Filled by | State |
| --- | --- | --- |
| [install-enable](install-enable.md) | US-1.1 | complete |
| [worker-start-stop-health](worker-start-stop-health.md) | US-1.2, US-2.2 | worker complete; model servers pending |
| [model-download-convert](model-download-convert.md) | US-2.4 | skeleton |
| [corpus-import-reindex-backup-restore](corpus-import-reindex-backup-restore.md) | US-4.1, US-4.3 | skeleton |
| [upgrade](upgrade.md) | US-1.5, later migrations | complete for EPIC-1 |
| [troubleshooting](troubleshooting.md) | US-1.5, US-2.3 | complete for EPIC-1 |
| [phi-purge](phi-purge.md) | US-4.5 | skeleton |
| [phi-incident](phi-incident.md) | Product Manager decision | skeleton, needs clarification |
| [phi-redaction](phi-redaction.md) | US-3.1, US-3.2 | complete |
