<p align="center">
  <img src="plugin/assets/claimcoach-logo.svg" width="72" height="72" alt="ClaimCoach logo">
</p>

# ClaimCoach developer guide

How ClaimCoach runs, from a clean Mac to the everyday start, and a reference for its models, REST
API, database, storage, and uploads. For what ClaimCoach is and who it is for, see
[README.md](README.md). Product: [PRD.md](PRD.md). Backlog: [SPECS.md](SPECS.md). Operations:
[docs/runbooks/](docs/runbooks/README.md).

- [App flows](#app-flows)
- [Models](#models)
- [Install (first run)](#install-first-run)
- [Start (every day)](#start-every-day)
- [Configuration](#configuration)
- [REST API](#rest-api)
- [Database schema](#database-schema)
- [Corpus and storage](#corpus-and-storage)
- [Uploads](#uploads)
- [Develop](#develop)
- [Troubleshooting](#troubleshooting)

## App flows

ClaimCoach is one Hermes Desktop plugin package with three halves: the desktop pane
(`plugin/desktop/plugin.js`), the gateway routes (`plugin/dashboard/plugin_api.py`), and the agent
tools (`plugin/__init__.py`). Heavy work runs in an app-owned **worker** on `127.0.0.1:18200`
([ADR-0001](docs/adr/0001-worker-sidecar.md)), which starts local model servers on
`127.0.0.1:18201`–`18219`.

**For stakeholders: what stays on the Mac.** Case documents go from the pane to the worker and the
local models only. The Hermes chat agent, which may run on a cloud model, gets case IDs, codes,
payer names, and redacted summaries, never a document.

![ClaimCoach PHI boundary: everything that reads a case stays on the Mac](docs/assets/flow-stakeholder.svg)

**For billers: a case from upload to outcome.** Each step names the local model that does it. A
person reviews every draft; nothing is sent to a payer.

![A ClaimCoach case: upload, extract, confirm, diagnose, draft, export, outcome](docs/assets/flow-user.svg)

**For developers: one request.** The pane calls `ctx.rest`; Hermes mounts `plugin_api.py` at
`/api/plugins/claimcoach/`; the gateway proxies to the worker with the per-launch token. A long
job answers at once with a `job_id`; while it runs, the gateway long-polls the worker's
`/jobs/{job_id}/events` and publishes each event to the pane as `plugin.claimcoach.case.progress`.

![A ClaimCoach request: pane, gateway, worker, model servers, and progress events](docs/assets/flow-request.svg)

## Models

ClaimCoach reads weights in place from `MODELS_HOME` (default `~/Models`) and never copies them.
Each role is one entry in `models.yaml` (defaults: `plugin/claimcoach/models/models.default.yaml`).
A role's server starts on first use, is health-checked, and unloads after `idle_timeout_s` (600 s).
The memory guard never keeps two models of 14B or more loaded at once, and transcription runs only
when nothing else is loaded. Roles on the same port share one server.

| Role | Model folder in `MODELS_HOME` | Source | Venv | Port | Tier | What ClaimCoach uses it for |
| --- | --- | --- | --- | --- | --- | --- |
| `extraction` | `Qwen3-VL-8B-Instruct-4bit` | `mlx-community/Qwen3-VL-8B-Instruct-4bit` | `mlx-vlm` | 18201 | 8B | Reads EOB/ERA PDF pages, images, and letters into structured case fields (US-5.2) |
| `phi_detection` | `Qwen3-8B-4bit` | `mlx-community/Qwen3-8B-4bit` | `mlx-lm` | 18202 | 8B | Finds PHI spans (with regex validators) to redact logs and agent tool results; the fine-tune export is checked with the regex validators (US-3.1) |
| `classification` | `Qwen3-8B-4bit` | `mlx-community/Qwen3-8B-4bit` | `mlx-lm` | 18202 | 8B | Classifies the denial reason and the appeal likelihood (US-6.1) |
| `embedding` | `Qwen3-Embedding-8B-4bit-DWQ` | `mlx-community/Qwen3-Embedding-8B-4bit-DWQ` | `mlx-lm` | 18203 | 8B | Embeds the global corpus at import and reindex (US-4.1, US-4.3); the retrieval query too, once a step uses retrieval (US-4.4) |
| `rerank` | `Qwen3-Reranker-8B-MLX-4bit` | converted locally from `Qwen/Qwen3-Reranker-8B` | `mlx-lm` | 18204 | 8B | Reranks retrieval candidates (US-4.4). Built and tested, but no pipeline step calls retrieval yet, so it does not start in a case flow |
| `explanation` | `Qwen3-14B-4bit` | `mlx-community/Qwen3-14B-4bit` | `mlx-lm` | 18205 | 14B | Writes the plain-language explanation and the missing-documentation checklist (US-6.2) |
| `drafting` | `Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` | `Youssofal/Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` | `mtplx` | 18206 | 27B | Drafts the appeal letter (US-7.1) and the corrected claim (US-7.4) |
| `transcription` | `Voxtral-Small-24B-2507-4bit` | `mlx-community/Voxtral-Small-24B-2507-4bit` | `mlx-vlm` | 18207 | 24B | Transcribes recorded payer calls in the after-hours window (US-11.1) |

- The reranker's source folder, `Qwen3-Reranker-8B`, is read once by `make models-convert` to build
  `Qwen3-Reranker-8B-MLX-4bit`. After that, ClaimCoach never reads it.
- These folders are the only ones ClaimCoach needs. Other folders in `~/Models` belong to other
  apps and are never read.
- Venvs live in `MODELS_HOME/.venvs/`. ClaimCoach does not create `mlx-lm`, `mlx-vlm`, or `mtplx`;
  `make doctor` and `make models-check` report a missing one. The worker's own venv is
  `MODELS_HOME/.venvs/claimcoach` (`make worker-venv`).
- Peak memory is about 22–28 GB with models loaded in sequence (PRD §8).

## Install (first run)

Prerequisites: an Apple-silicon Mac, Hermes Desktop with Hermes Agent 0.22.5 or later (`hermes` on
the `PATH`), `uv`, Node.js 22.15 or later with `npm`, `openspec` (for delivery), and `curl` and
`lsof`. The model venvs must exist in `MODELS_HOME/.venvs/` with what each role runs: `mlx-lm` with
`mlx-lm` and `huggingface_hub` (it also runs the downloads and the conversion), `mlx-vlm` with
`mlx-vlm` and `mlx-audio`, and `mtplx`. `make models-check` only sees whether a venv's Python
exists; see [model-download-convert](docs/runbooks/model-download-convert.md) for the packages.

1. Install the dev dependencies (uv and npm) and the pre-commit hook:

   ```bash
   make install
   ```

2. Check tools, venvs, `MODELS_HOME`, the plugin link, and the worker. It installs nothing, but
   writes the default `models.yaml` if there is none yet:

   ```bash
   make doctor
   ```

3. Create the worker venv (Python 3.12) at `MODELS_HOME/.venvs/claimcoach`:

   ```bash
   make worker-venv
   ```

4. Write the default `models.yaml` to the data dir (it never overwrites an edited copy), then list
   each role's weights and venv:

   ```bash
   make models-init
   ```

   ```bash
   make models-check
   ```

5. Start the worker. Downloads and corpus imports go through it. Model servers start only on first
   use, so missing weights don't stop it:

   ```bash
   make start
   ```

6. Download each role that `make models-check` shows as `missing`. Downloads run only with
   `CONFIRM=yes`, and Claude Code's project settings deny them to agents. Each one runs in the
   background; `make models-status` shows `acquire: downloading` until it ends:

   ```bash
   make models-download ROLE=extraction CONFIRM=yes
   ```

   The reranker is downloaded from its official source, then converted on this Mac with no
   network. It is optional for now: no pipeline step calls retrieval yet.

   ```bash
   make models-download ROLE=rerank CONFIRM=yes
   ```

   Wait until `make models-status` shows `rerank` with `source_present: true` and no `acquire`;
   before that, the conversion only answers `in_progress`. Then convert:

   ```bash
   make models-convert CONFIRM=yes
   ```

7. Link the package into Hermes, enable the Python half, and restart the gateway:

   ```bash
   make plugin-install
   ```

8. Enable the desktop half: Hermes Desktop → **Capabilities → Plugins** → **Rescan** → switch on
   **ClaimCoach**.

9. Load the global corpus (rule cards, codes, letter templates) from a local bundle file. The
   `embedding` model must be downloaded first. The settings page's **Import corpus** does the same
   with a preview:

   ```bash
   make corpus-import FILE=rules.yaml
   ```

10. Check the worker's health and the models:

    ```bash
    make worker-health
    ```

    ```bash
    make models-status
    ```

Every role reports `unloaded` until its first use. Open the **ClaimCoach** pane and drop a denial
document to create the first case. Details: [install-enable](docs/runbooks/install-enable.md),
[model-download-convert](docs/runbooks/model-download-convert.md).

## Start (every day)

Once ClaimCoach is installed, start the worker; it waits until `/health` answers with a new token:

```bash
make start
```

See each model server's state (`unloaded`, `queued`, `starting`, `ready`, `unhealthy`,
`stopping`):

```bash
make models-status
```

Stop the worker at the end of the day. It stops every model server it started:

```bash
make stop
```

Model servers start on first use, so the first extraction or draft of the day waits for its model
to load. To warm one up first, run `make models-load ROLE=drafting`. After a `git pull`, follow
[upgrade](docs/runbooks/upgrade.md): stop the worker, reinstall, restart the gateway and the
worker, and **Rescan** in Hermes Desktop, which runs its own copy of `plugin.js`. Details:
[worker-start-stop-health](docs/runbooks/worker-start-stop-health.md).

## Configuration

### Plugin settings

Set in Hermes Desktop's settings form for ClaimCoach (`plugins.entries.claimcoach.settings`).
`plugin/plugin.yaml`'s `config_schema` mirrors `ClaimCoachSettings` (`plugin/claimcoach/settings.py`),
and a test fails when they drift.

| Setting | Default | Meaning |
| --- | --- | --- |
| `models_home` | `~/Models` | Declared, but not read yet: the worker takes the weights folder from `MODELS_HOME` in its environment (`make start MODELS_HOME=/Volumes/Models`). |
| `retention_days` | `90` | Days after a case closes before its source documents are purged. Also on the settings page. |
| `richer_agent_access` | `false` | Reserved for a local Hermes model; shown in the statusbar. Agent tool results stay redacted. |
| `share_outcome_stats` | `false` | Shares this profile's de-identified outcomes with the manager's weekly summary and fine-tune export. |
| `transcription_start_hour` | `19` | Hour (0–23, this Mac's time) after which payer calls are transcribed. |
| `transcription_end_hour` | `7` | Hour (0–23) after which no new call starts transcribing. |

### `models.yaml`

`make models-init` copies the defaults to `<hermes root>/plugin-data/claimcoach/models.yaml` on the
first run and never overwrites an edited copy. Edit that copy, not the defaults. Each role sets
`model_dir`, `repo_id` (or `convert`), `venv`, `command`, `port`, and `tier_b`. The file also sets
`idle_timeout_s` (600), `queue_timeout_s` (900), and the memory guard's
`large_tier_b` (14), under `residency`.
Command placeholders: `{venv}`, `{model}`, `{host}` (always `127.0.0.1`), `{port}`, and
`{logs}`. Check an edit with `make models-check`.

### Make variables and environment

Override a variable per command, for example `make start MODELS_HOME=/Volumes/Models`. Per-target arguments
(`ROLE`, `CASE`, `FILE`, `CONFIRM`, …) are listed with each target by `make`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MODELS_HOME` | `~/Models` | Model weights and venvs. Also read by the code from the environment. |
| `HERMES_HOME` | `~/.hermes` | Hermes root: plugin data, profiles, and the plugin link. Also read by the code. |
| `HERMES` | `hermes` | The Hermes CLI. |
| `UV` | `uv` | Python package manager. |
| `NPM` | `npm` | Node package manager (dev tooling only; nothing ships). |
| `WORKER_VENV` | `$(MODELS_HOME)/.venvs/claimcoach` | The worker's venv. |
| `WORKER_PYTHON` | `$(WORKER_VENV)/bin/python` | The worker's interpreter. |
| `WORKER_PORT` | `18200` | The worker's loopback port. The pane, gateway, and agent tools always use 18200; another port is only for a scratch worker with its own `HERMES_HOME`. Model servers use 18201–18219. |
| `PLUGIN_LINK` | `$(HERMES_HOME)/plugins/claimcoach` | Where `make plugin-link` points at `plugin/`. |
| `OPENSPEC` | `openspec` | OpenSpec CLI for the delivery flow. |
| `OHMYORCH` | `~/sites/OhMyOrch/plugins/ohmyorch/bin/ohmyorch` | Evidence report validator, when installed. |

## REST API

The desktop pane calls these routes with `ctx.rest`. Hermes mounts them at
`/api/plugins/claimcoach/` inside its gateway. Each one proxies to the worker, except `/settings`
and `/settings/retention`, which the gateway answers from Hermes' plugin settings. A route answers
a typed model with `"ok": true`, or the error envelope
`{"ok": false, "error": {"code": "...", "message": "..."}}` with a fixed message per code
(`plugin/claimcoach/api/models.py`). Errors never echo document text. A route with a body reads
JSON unless it says `multipart`; jobs answer at once and report progress as
`plugin.claimcoach.case.progress` events. No route sends anything to a payer (BR-4).

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/health` | — | `HealthResponse`: `status`, `version` |
| GET | `/settings` | — | `SettingsResponse`: `richer_agent_access`, `retention_days` |
| POST | `/settings/retention` | `{"retention_days": 90}` | `SettingsResponse` |
| GET | `/corpus/status` | — | `CorpusStatusResponse`: `global_scope`, `user_scopes` (paths, counts, encryption, index model) |
| GET | `/models/status` | — | `ModelsStatusResponse`: `idle_timeout_s`, per role `state`, `port`, `weights`, `venv_present`, `acquire` |
| POST | `/models/download` | `{"role": "explanation", "confirm": true}` | `AcquireResult`: `role`, `outcome` (`started`, `in_progress`, `present`, or `declined` without `confirm: true`) |
| POST | `/models/convert` | `{"role": "rerank", "confirm": true}` | `AcquireResult` |
| POST | `/cases` | `{}` | `Case` (new, open, empty) |
| GET | `/cases` | — | `CaseList`: newest cases with dates, outcome, counts, and steps; no case content |
| GET | `/cases/{case_id}` | — | `Case`: documents, extraction, fields to confirm, diagnosis, deadline, draft, remedy, correction, outcome, calls |
| POST | `/cases/{case_id}/documents` | multipart `file` (PDF, PNG, JPEG, text) | `DocumentAdded`: `case_id`, `document` |
| POST | `/cases/{case_id}/paste` | `{"text": "ISA*00*..."}` (835 or letter text) | `DocumentAdded` |
| POST | `/cases/{case_id}/calls` | multipart `file` (WAV, MP3, FLAC, M4A) | `CallAdded`: `case_id`, `call` |
| POST | `/cases/{case_id}/calls/{call_id}/transcribe` | `{}` | `TranscriptionQueued`: `case_id`, `job` (state, window, `not_before`) |
| POST | `/cases/{case_id}/process` | `{}` | `JobStarted`: `job_id`, `kind: "extract"` |
| POST | `/cases/{case_id}/fields` | `{"path": "claim_id", "value": "CLAIM-77"}` | `Case` (the value stored as confirmed) |
| POST | `/cases/{case_id}/diagnose` | `{}` | `JobStarted`: `kind: "diagnose"` |
| POST | `/cases/{case_id}/draft` | `{"template_id": null}` | `JobStarted`: `kind: "draft"` |
| POST | `/cases/{case_id}/draft/text` | `{"text": "..."}` (the biller's edits) | `Case` |
| POST | `/cases/{case_id}/export` | `{"format": "pdf"}` (`pdf` or `docx`) | `ExportedFile`: `path`, `filename`, `size_bytes`, `expires_at` (for the host's save dialog) |
| POST | `/cases/{case_id}/correction` | `{}` | `JobStarted`: `kind: "correct"` |
| POST | `/cases/{case_id}/correction/export` | `{"format": "docx"}` | `ExportedFile` |
| POST | `/cases/{case_id}/outcome` | `{"outcome": "overturned"}` (`overturned`, `upheld`, `written_off`) | `Case` (now closed) |
| GET | `/outcomes/summary` | query `week=2026-W44` (optional) | `WeeklySummary`: totals and overturn rates per payer, reason, and code of opted-in profiles |
| POST | `/outcomes/export` | `{"approval": {"manager": "Dana Lee", "approved": true}}` | `FineTuneExport`: `path`, `records`, `withheld`, `approved_by` |
| POST | `/corpus/import/preview` | multipart `file` (`.yaml`, `.yml`, or `.json` bundle) | `BundlePreview`: `valid`, `problem` (where it failed, never file text), `items`, `by_kind`, `replaces`; writes nothing |
| POST | `/corpus/import` | query `confirm=true`, multipart `file` | `ImportResult`: `imported` per kind, `chunks`; 409 `import_not_confirmed` without `confirm=true` |

**Worker-only routes.** The worker (`127.0.0.1:18200`, `Authorization: Bearer <per-launch
token>`) serves what the gateway proxies to. The gateway's `/process` calls the worker's
`/extract`, and `/corpus/import/preview` validates the bundle in the gateway and reads the worker's
`GET /corpus/global` to say what it replaces. These worker routes are called only by
`plugin_api.py`, the agent tools, and the `make` targets: `GET /egress`, `POST /redact`, `GET /corpus/global`,
`POST /corpus/reindex`, `POST /corpus/purge`, `GET /corpus/audit`, `POST /models/{role}/load`,
`POST /models/{role}/unload`, `GET /jobs/{job_id}/events`,
`GET /transcriptions`, `POST /agent/explain-code`, `POST /agent/rule-cards`, and
`POST /agent/case-summary`.

**Agent tools.** `claimcoach_explain_code` (a CARC/RARC/group code), `claimcoach_payer_rules` (a
payer's rule cards), and `claimcoach_case_summary` (a case ID → a redacted summary). Each handler
redacts its own result; a `transform_tool_result` hook redacts again. The `/denial` slash command
and the `claimcoach:denial-triage` skill use them. `make agent-tools` lists their schemas.

## Database schema

Each corpus scope is two WAL SQLite files with `secure_delete` on: `corpus.sqlite3` (content) and
`index.sqlite3` (vectors), attached as `main` and `idx`. Every table but `audit_log` is `STRICT`.
In the user scope,
every `body`, `payload`, `data`, and `vector` value is sealed with AES-256-GCM, bound to its row,
so a value copied onto another row fails to decrypt. IDs, kinds, and timestamps stay in clear. The key is in the macOS Keychain (service `ClaimCoach user store`). The schema
is `_SCHEMA` in `plugin/claimcoach/corpus/store.py`. Three pieces of code run SQL on these files:
`CorpusStore`; `read_outcomes`, a read-only connection that may read only `main.outcomes` (the
manager's summary and the fine-tune export); and `corpus/backup.py`, which copies whole files.
Older tables are migrated by checking their shape, not a version number.

| Table | Columns | Written by | Read by | PHI |
| --- | --- | --- | --- | --- |
| `main.meta` | `key`, `value` | `CorpusStore` on first open: `scope` (`global` or `user`), and in the user scope `key_check`, sealed with the Keychain key | `CorpusStore` on every open: another scope's files, or a key check that fails to decrypt, are refused | No |
| `main.cases` | `case_id`, `opened_at`, `closed_at`, `purged_at` | `POST /cases` (`create_case`); `POST /cases/{id}/outcome` sets `closed_at`; the retention purge sets `purged_at` | `GET /cases` (`case_index`), `GET /cases/{id}` (`open_case`), the retention purge (`expired_cases`) | No |
| `main.case_items` | `case_id`, `item_id`, `kind` (`source`, `extraction`, `diagnosis`, `draft`, `call`, `transcript`, `correction`), `created_at`, `payload`, `data` | Uploads, paste, extraction, field confirmation, diagnosis, draft and its edits, correction, call and transcript (`put_case_item`); deleted by the purge | `GET /cases/{id}`, `GET /cases` (`case_index`: item kinds only, nothing opened), every job that reads the case, exports, `claimcoach_case_summary` (redacted), the retention purge (`expired_cases`) | Yes, sealed |
| `main.documents` | `doc_id`, `case_id`, `kind`, `created_at`, `body` | Global scope: corpus import (`rule_card`, `code`, `letter_template`). User scope: `put_document` exists for case retrieval, but no pipeline step writes it yet | The exact lookups in `corpus/lookup.py` (`code_entries`, `payer_rule_cards`, `letter_template`), used by the diagnosis, the deadline and remedy, the appeal and corrected-claim drafts, and the agent tools; `GET /corpus/global` and the import preview; the purge | User scope: Yes, sealed |
| `main.chunks` | `chunk_id`, `doc_id`, `case_id`, `kind`, `ordinal`, `body` | With its document, cut into 1200-character chunks | Reindex; retrieval (`search`, `chunks`), which no pipeline step calls yet | User scope: Yes, sealed |
| `main.outcomes` | `case_id`, `outcome`, `recorded_at`, `features` (de-identified) | `POST /cases/{id}/outcome` (`record_outcome`), in the same transaction that closes the case | The weekly summary and the fine-tune export (`read_outcomes`, read-only, this table only), `GET /cases/{id}`, `GET /cases` (`case_index`) | No (de-identified) |
| `main.audit_log` | `seq`, `at`, `action`, `case_id`, `profile` | Every case access and change (`case_opened`, `case_extracted`, `draft_exported`, …). Triggers refuse updates and deletes | `make corpus-audit` (`GET /corpus/audit`) | No |
| `idx.meta` | `key`, `value` | `embedding_model_id` on first open and on reindex; `dimension` on the first insert, cleared by reindex | Every search and insert, and corpus status (`index_info`); a changed model or dimension refuses them until `make corpus-reindex` | No |
| `idx.vectors` | `chunk_id`, `case_id`, `vector` (float32, unit length) | Corpus import and reindex (`replace_index`), with each chunk | `search`: cosine similarity, filtered in SQL to the global scope plus the current case; no pipeline step calls it yet | User scope: Yes, sealed |

Files outside SQLite: the transcription queue (`queue.json`: IDs, states, dates, error codes) and
the fine-tune approval log (`approvals.jsonl`). Neither holds PHI.

## Corpus and storage

The **global** scope is shared by every Hermes profile on the Mac: CARC/RARC/group code notes,
payer rule cards (timely filing, appeal levels, required documents, submission, corrected claims),
and letter templates. Each rule card carries its `source` and `verified_on` date, and stale cards
are flagged. The **user** scope belongs to one profile (one biller) and holds that biller's cases.
Retrieval for a case would read the global scope plus that case only (BR-5); today the pipeline
reads the global scope by exact key (codes, payer rule cards, template IDs) instead.

| What | Path | Holds | PHI | Protection |
| --- | --- | --- | --- | --- |
| Global scope | `<hermes root>/plugin-data/claimcoach/global/` | `corpus.sqlite3`, `index.sqlite3`: rule cards, codes, templates | No | Folder `0700` |
| User scope | `<profile home>/plugin-data/claimcoach/user/` | `corpus.sqlite3`, `index.sqlite3`: cases, items, outcomes, audit log | Yes | AES-256-GCM per value, key in the Keychain; folder `0700` |
| Exports | `<profile home>/plugin-data/claimcoach/exports/` | Exported drafts (PDF, DOCX) for the save dialog | Yes | Deleted 15 minutes after they are written |
| Fine-tune exports | `<hermes root>/plugin-data/claimcoach/fine-tune/` | `fine-tune-*.jsonl` and `approvals.jsonl` | No (redacted) | Manager approval per export; `0600` |
| Transcription queue | `<hermes root>/plugin-data/claimcoach/transcription/` | `queue.json` | No | Written atomically, `0600` |
| Worker state | `<hermes root>/plugin-data/claimcoach/worker/` | `token` (per launch), `worker.json` (PID handle), `worker.log`, `egress.jsonl` (US-12.4 connection audit) | No | `token` and `worker.log` `0600`; token removed on stop |
| Model registry | `<hermes root>/plugin-data/claimcoach/models.yaml` | Model roles | No | Edited by the operator only |
| Model servers | `<hermes root>/plugin-data/claimcoach/models/` | `servers.json` (running servers, for orphan cleanup), `<port>.log` per server, `server-logs/`, `acquire-<role>.log` | No, but a model server's own output is not filtered | Folder `0700`, logs `0600` |
| Transcription temp file | `/tmp/*_*.wav` | The decoded call `mlx_audio.server` writes while it transcribes | Yes | Owner-only (the server runs with umask `077`); left behind only by a crash or a forced stop, then removed by hand ([payer-call-transcription](docs/runbooks/payer-call-transcription.md)) |
| Model weights | `MODELS_HOME/<model_dir>/` | Weights, read in place | No | Never copied |

`<hermes root>` is `~/.hermes`. The default profile's home is the root itself; another profile's
home is `<hermes root>/profiles/<name>`. Nothing is stored in the install dir (`plugin/`).

- **Import:** `make corpus-import FILE=rules.yaml` or the settings page (preview, then confirm). A
  bundle is a local YAML or JSON file with `items` of kind `rule_card`, `code`, or
  `letter_template`; nothing is fetched. The bundle format is in
  `plugin/claimcoach/corpus/bundle.py`.
- **Retention:** source documents are purged `retention_days` after the case closes. Outcomes are
  kept de-identified. `make corpus-purge` runs it now.
- **Backup and restore:** `make corpus-backup` copies both scopes as stored (encrypted);
  `make corpus-key-export` saves a profile's key. See
  [corpus-import-reindex-backup-restore](docs/runbooks/corpus-import-reindex-backup-restore.md).

## Uploads

A **document** or **call recording** goes pane → `ctx.rest` (one `multipart/form-data` part named
`file`) → `plugin_api.py`, which reads the body in memory up to its limit and forwards it unparsed →
the worker, which parses the part, decides the type from the file's bytes (never its name or
declared type), and seals it into the case. Starlette's form parser is not used, because it spools
large parts to an unencrypted temporary file. **Pasted text** is a JSON body, `{"text": "..."}`.
A **corpus bundle** is different: it holds no PHI, so the gateway parses and validates it itself
(the file must be named `.yaml`, `.yml`, or `.json`) and sends the worker the validated items as
JSON. A refused upload is not stored.

| Upload | Route | Accepted | Limit | Where it goes |
| --- | --- | --- | --- | --- |
| Denial document | `POST /cases/{case_id}/documents` | PDF, PNG, JPEG, text (835 or letter) | 16 MiB | A `source` case item; refused once the case is closed (`case_closed`) |
| Pasted text | `POST /cases/{case_id}/paste` | 835 or letter text | 4 MiB | A `source` case item of kind `edi_835` or `text` |
| Payer-call recording | `POST /cases/{case_id}/calls` | WAV, MP3, FLAC, M4A | 128 MiB | A `call` case item; transcribed later into a `transcript` item |
| Corpus bundle | `POST /corpus/import/preview`, then `POST /corpus/import?confirm=true` | YAML or JSON, up to 5000 items | 5 MiB | Global scope documents, chunks, and vectors |

A document or paste that is too large answers `document_too_large` (`call_too_large` for calls),
and an unknown type answers `unsupported_document` (`unsupported_audio`). A bad or too-large bundle
answers the preview with `valid: false` and a `problem` naming where it failed, never text from the
file; the import answers `invalid_bundle` with a fixed message, or `import_not_confirmed` without
`confirm=true`.

## Develop

```bash
make check
```

`make check` is the quality gate (ES-7): ruff, ruff format, biome, mypy `--strict`, tsc
`--checkJs`, offline pytest and `node --test`, each with 100% coverage. `make verify` also checks
the evidence and runs the gate's own self-tests. `make` lists every target.

```text
plugin/                     # the Hermes package (symlinked to ~/.hermes/plugins/claimcoach)
├── plugin.yaml             # manifest v2; config_schema mirrors ClaimCoachSettings (drift-tested)
├── __init__.py             # agent half: register(ctx) → claimcoach_* tools
├── assets/                 # claimcoach-logo.svg, shared by the READMEs and plugin.js
├── dashboard/              # backend half: manifest.json + plugin_api.py (router)
├── desktop/plugin.js       # desktop half (plain ESM, // @ts-check) + tests/ (node --test)
├── skills/denial-triage/
└── claimcoach/             # app package: api/, worker/, models/, corpus/, cases/, pipeline/, …
tests/                      # pytest: test_us_<epic>_<n>_*.py, fakes/, hermes/ probe
docs/runbooks/ · docs/adr/ · docs/assets/
evidence/US-x.y/            # test reports + JUnit
openspec/                   # OpenSpec changes (one per story) and specs
```

Delivery flow per story: OpenSpec change (`openspec/changes/us-x-y-*`) → implementation and tests
→ `make check` → `make evidence STORY=US-x.y` + `evidence/US-x.y/test-report.md` →
`make evidence-check` → independent review → `openspec archive`. In Claude Code the
`deliver-story` skill (`.claude/skills/`) runs this flow; project hooks format Python on every
edit, keep `openspec/specs/` and archived changes immutable, and deny agents model downloads.

Release: every EPIC-12 gate must pass against the running worker and the real local models:
`make release-gate` ([evals-release-gates](docs/runbooks/evals-release-gates.md)).

## Troubleshooting

- **`make models-check` refuses `models.yaml` (for example, an unknown placeholder).** The copy in
  the data dir came from another checkout or version. Move it aside and run `make models-init`; see
  [upgrade](docs/runbooks/upgrade.md).
- **A role stays `queued`.** The memory guard is waiting for a large model to unload; see
  `make models-status` and [troubleshooting](docs/runbooks/troubleshooting.md).
- **The pane says the worker is unavailable.** Run `make start`, then `make worker-health`.
- **Search refuses with `index_stale`.** The embedding model changed; run
  `make corpus-reindex SCOPE=global`, and `make corpus-reindex SCOPE=user PROFILE=<name>` for each
  profile.
