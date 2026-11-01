# Runbook: Upgrade ClaimCoach

Rules: PC-2 (Desktop runs a copy of `desktop/plugin.js`), PC-5, ES-7. Later stories add data
migrations here as they introduce stored data.

## Preconditions

- `make check` passes on the target revision.
- The worker is stopped: `make worker-stop`.
- A backup of the data dir if the release notes mention a data migration
  ([corpus runbook](corpus-import-reindex-backup-restore.md)).

## Steps

1. Update the checkout and dependencies:

   ```bash
   git pull --ff-only
   make install
   make worker-venv
   ```

2. Re-validate and restart:

   ```bash
   make validate
   hermes gateway restart
   make worker-start
   ```

3. Refresh the desktop copy: Hermes Desktop → **Capabilities → Plugins** → **Rescan**.

## Verification

```bash
hermes plugins doctor claimcoach
make worker-health
```

- `doctor` reports no stale desktop copy; `worker-health` reports the new version.

### Data migrations

| From | Migration | Runs | Checked by |
| --- | --- | --- | --- |
| before US-6.1 | Each user store's `case_items` table is rebuilt once so its CHECK accepts every case-item kind (`diagnosis` from US-6.1); rows are copied unchanged, in one transaction | When the worker first opens the store | `test_us_6_1_case_items_check_migrates` |
| before US-6.3 | None at upgrade: an extraction stored earlier reads its new `denial_date` field as unreadable. Every extraction stored or confirmed afterwards holds `denial_date`, which an earlier version refuses to read | — | `test_us_6_3_older_extraction_loads` |
| before US-7.1 | The same `case_items` rebuild, once, so the CHECK accepts `draft` | When the worker first opens the store | `test_us_7_1_a_us_6_store_accepts_drafts` |
| before US-8.2 | `ALTER TABLE outcomes ADD COLUMN features TEXT`, once; existing outcomes keep `NULL` and count as unclassified in the weekly summary and as unlabeled in the fine-tune export | When the worker first opens the store | `test_us_8_2_an_older_outcomes_table_gains_features` |

### Configuration changes

The worker copies `models.default.yaml` to `<hermes root>/plugin-data/claimcoach/models.yaml` once,
on its first start; later changes to the shipped file reach an existing copy only by hand, unless
the table below says the worker migrates it.

| From | Change to the copy | Why |
| --- | --- | --- |
| before US-7.1 | The worker adds `"--reasoning", "off"` to the `drafting` role's `command` on its next start when the copy still holds the old shipped line unchanged (`test_us_7_1_unedited_drafting_command_migrates`). If you edited that line, append `"--reasoning", "off"` to its list yourself, then `make worker-stop` and `make worker-start` | With the default (`auto`), Bonsai 27B's hidden reasoning spends the reply's token budget and every draft ends `drafting_failed` ([appeal-drafting](appeal-drafting.md)) |
| before US-8.2 | None: `share_outcome_stats` is off until a profile turns it on in Settings → Plugins → ClaimCoach. An earlier version that reads a config holding it treats the unknown key as invalid and uses its defaults for the settings it reads through Hermes (richer agent access stays off; retention is read on its own) | Sharing outcomes with the manager is opt-in (US-8.2) |
| before US-11.1 | The worker replaces the `transcription` role's `command` on its next start when the copy still holds the old shipped line unchanged: `"--model", "{model}"` goes and `"--log-dir", "{logs}"` is appended (`test_us_11_1_unedited_transcription_command_migrates`). If you edited that line, make the same change yourself, then `make worker-stop` and `make worker-start`. New settings `transcription_start_hour` (19) and `transcription_end_hour` (7) need nothing | `mlx_audio.server` has no `--model` flag, so the old command never starts and every call ends `model_unavailable` ([payer-call-transcription](payer-call-transcription.md)) |
| before US-14.1 | None: the worker ignores the copy's `rerank` role and `acquire.convert` command and leaves the file as it is (`test_us_14_1_old_registry_still_loads`). You may delete both entries by hand. A role you changed to `convert` by hand now needs a `repo_id` instead, or the worker refuses the file. `Qwen3-Reranker-8B` and `Qwen3-Reranker-8B-MLX-4bit` under `MODELS_HOME` are no longer read; remove them by hand if nothing else uses them. An earlier version refuses a copy without the `rerank` role, so keep the old copy if you may roll back | No case flow used retrieval; the diagnosis and the drafts read rule cards, codes, and templates by exact key ([model-download-convert](model-download-convert.md)) |
| before US-14.2 | None: a `models_home` value a profile saved is ignored, and the profile's other settings keep their values (`test_us_14_2_saved_models_home_ignored`). Set the weights folder with `MODELS_HOME` when you start the worker | Settings belong to one profile, and the worker every profile shares reads `MODELS_HOME` |

## Rollback

```bash
make worker-stop
git checkout <previous tag or commit>
make install && make worker-venv
hermes gateway restart
make worker-start
```

Then **Rescan** in Capabilities → Plugins.

An earlier version opens a store migrated by a later one (the CHECK only grew) and ignores the
case items it does not know, such as diagnoses. It cannot read an extraction stored or confirmed
by US-6.3 or later (its model forbids the `denial_date` field), so such a case would not open:
rolling back past US-6.3 means restoring the backup taken before the upgrade
([corpus runbook](corpus-import-reindex-backup-restore.md)), which loses the work done since.

Before US-8.1 no route recorded an outcome, so a store has outcome rows only from this version on.
An earlier version reads them (it selects the columns it knows) but cannot record one into the
four-column table; rolling back past US-8.1 loses only the ability to mark outcomes.
