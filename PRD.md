# ClaimCoach: PRD

| | |
| --- | --- |
| Status | Draft v0.1 (2026-10-30) |
| Workflow step | 1 of 4: **PRD** → specs → plan → implement |
| RFS | YC Winter 2027, "The $15-an-Hour Expert" |
| Ships as | Hermes Desktop plugin package `claimcoach` |
| Runs on | Local models in `~/Models` (8B–27B MLX), Apple M3 Pro, 36 GiB |

ClaimCoach is a standalone app. It shares no code, corpus, processes, or data with PermitPilot or ModelForge. The only thing it has in common with them is that it reads model weights from `~/Models`.

## 1. Summary

ClaimCoach turns an entry-level medical biller into a denial-management specialist. The biller drops a denied claim (EOB/ERA, CARC/RARC codes, the payer's letter) into a Hermes Desktop pane. ClaimCoach redacts PHI for logging, explains in plain language why the claim was denied, estimates whether an appeal is worth filing, lists missing documentation, and drafts the appeal letter or corrected claim for human review. Each case ends with a checklist the biller learns from. **PHI never leaves the Mac.**

## 2. Problem

- Claim denials are routine. Working them takes specialist knowledge: code meanings, payer-specific rules, appeal deadlines, and what documentation wins.
- Small practices and billing services staff these roles with entry-level people who lack that knowledge, so they write off recoverable revenue or file weak appeals.
- Cloud AI tools are a hard sell. The documents are full of PHI, and every vendor adds a BAA and a data-flow review.

## 3. Personas

| Persona | Need |
| --- | --- |
| **Entry-level biller / front-desk staff** (primary) | Know what to do with a denial without escalating every case |
| **Billing manager at a small practice or billing service** | Higher overturn rate, consistent appeals, visibility into denial patterns |
| **Practice owner** | Recover revenue without sending PHI to a cloud vendor |

## 4. Goals and success metrics

| Goal | Metric | v1 target |
| --- | --- | --- |
| Correct diagnosis | Denial-reason classification accuracy on a labeled set of de-identified cases | ≥ 85% |
| Useful drafts | Appeal letters accepted with only minor edits (manager review rubric) | ≥ 70% |
| Faster work | Median time from denial upload to appeal-ready draft | ≤ 10 min (vs. ~45 min baseline, to be measured) |
| Safe logs | PHI recall of the redactor on a synthetic PHI test set (names, DOB, MRN, member ID, SSN, address, phone) | ≥ 98% |
| Fully local | Outbound network calls carrying case content | 0 |

## 5. Non-goals (v1)

- EHR, practice-management, or clearinghouse integrations (upload and paste only).
- Submitting appeals or claims to payers.
- Coding new claims (CPT/ICD assignment) or giving medical or legal advice.
- Multi-site/multi-tenant administration. v1 is one Mac, one or a few Hermes profiles.
- Billing for the app itself.

## 6. v1 scope: user stories

1. As a biller, I open the **ClaimCoach** pane, create a case, and drop in the EOB/ERA (PDF or image) plus the denial letter, or paste 835 text.
2. ClaimCoach extracts the claim lines, CARC/RARC/group codes, dates, and amounts into a structured case, and highlights any field it couldn't read for me to confirm.
3. I see a **plain-language explanation** of the denial, the likely root cause, an **appeal-likelihood** (low/medium/high with reasons), the appeal deadline, and a **missing-documentation checklist**.
4. I click **Draft appeal**. ClaimCoach drafts the letter from the payer's rule card and a template. I edit it in the pane and export it as PDF/DOCX. I never auto-send.
5. I mark the case outcome later (overturned/upheld/written off). That outcome feeds the manager's dashboard and the future fine-tune set.
6. I can ask the Hermes agent "what usually fixes CO-197 for this payer?". The agent answers from the **global corpus** without seeing my case's PHI (see §7.2).
7. As the manager, I maintain the global corpus (code knowledge base, payer rule cards, letter templates) and review a weekly denial-pattern summary per payer/code.
8. (v1.1) I attach a recorded payer call. ClaimCoach transcribes it after hours and adds the reference number and rep instructions to the case.

## 7. Architecture: Hermes Desktop plugin package

ClaimCoach is one **unified Hermes plugin package** (the Python agent half and the desktop UI half in one folder).

```text
claimcoach/                       # this project folder
├── PRD.md
├── SPECS.md                      # workflow step 2 (OhMyOrch ingest-spec backlog)
├── docs/runbooks/ · docs/adr/    # §13 ES-6, ES-9
├── evidence/US-x.y/              # §13 ES-5 test reports
└── plugin/                       # symlinked → ~/.hermes/plugins/claimcoach
    ├── plugin.yaml               # name: claimcoach, version, manifest_version, api_version
    ├── __init__.py               # register(ctx): tools, hooks, slash commands, CLI, skills
    ├── skills/denial-triage/     # agent skill: triage + explanation playbook (no PHI)
    ├── dashboard/
    │   ├── manifest.json         # { "name": "claimcoach", "api": "plugin_api.py" }
    │   └── plugin_api.py         # FastAPI router → /api/plugins/claimcoach/*
    ├── desktop/
    │   └── plugin.js             # case pane, case route, manager dashboard route, settings
    └── claimcoach/               # app package: models/, corpus/, redact/, pipeline/, letters/
```

| Half | Responsibilities | Hermes surface |
| --- | --- | --- |
| **Agent (Python)** | PHI-free tools: `claimcoach_explain_code`, `claimcoach_payer_rules`, `claimcoach_case_summary` (returns redacted summaries by case ID only). Slash command `/denial`. CLI `hermes claimcoach corpus ...` | `ctx.register_tool`, `register_command`, `register_cli_command`, `register_skill`, `register_hook("transform_tool_result")` as a final redaction guard |
| **Backend** | Case store, extraction, redaction, classification, drafting, model process manager, corpus API, outcome tracking; progress events | `plugin_api.py`; `broadcast_plugin_event("claimcoach", ...)` |
| **Desktop (JS)** | Case list + case detail pane, letter editor, manager dashboard route, statusbar "local-only" indicator, settings (models, corpus, retention) | `ctx.register`, `ctx.rest`, `host.onEvent`, `ctx.files.requestFolder()`, `registerSettingsPage` |

### 7.1 Install/dev

`ln -s <repo>/claimcoach/plugin ~/.hermes/plugins/claimcoach`, then `hermes plugins enable claimcoach` (Python half) and enable the desktop half in **Capabilities → Plugins**. Both are opt-in by default. State lives in `plugin_data_dir("claimcoach")`, never in the install dir.

### 7.2 The PHI boundary (key requirement)

The Hermes **chat agent** may run on a cloud model, and anything returned to it as a tool result can leave the Mac. So:

- **All PHI flows go desktop pane → `plugin_api.py` → local models.** They never pass through the agent transcript.
- Agent tools only accept/return **case IDs, codes, payer names, and redacted summaries**. Each tool handler redacts its own result **before returning** (primary guard). A `transform_tool_result` hook runs the redactor again as a defense-in-depth second guard only, because that hook is fail-open (§7.9 PC-7).
- If the user's Hermes model is a local endpoint, a setting can allow richer agent access. It's off by default and shown in the statusbar.

### 7.9 Verified platform constraints and the worker decision

Checked on 2026-10-30 against the Hermes Desktop Plugin SDK and plugins docs and the local Hermes Agent **v0.22.5** source (`~/.hermes/hermes-agent`). Stories cite these IDs.

| ID | Constraint |
| --- | --- |
| PC-1 | The Python half loads only when `claimcoach` is in `plugins.enabled` (`hermes plugins enable claimcoach`). The desktop half is enabled separately in **Capabilities → Plugins**. Both are off by default. |
| PC-2 | Unified package layout: `plugin.yaml`, `dashboard/manifest.json` (`{"name": "claimcoach", "api": "plugin_api.py"}`), `dashboard/plugin_api.py` exporting a FastAPI `router` mounted at `/api/plugins/claimcoach/`, and `desktop/plugin.js`. Dev installs symlink the package into `~/.hermes/plugins/claimcoach`. Desktop runs a copy in `desktop-plugins/claimcoach/`, and `hermes plugins doctor claimcoach` warns when that copy is stale. |
| PC-3 | `desktop/plugin.js` is plain ESM with no build step and no JSX (`jsx()`/`jsxs()` from `react/jsx-runtime`). It may import only `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime`. `ctx.files` text reads/writes are capped at 4 MiB. Optional SDK calls must be feature-detected. |
| PC-4 | `plugin_api.py` runs inside the gateway process. Plugin websockets are refused for secondary served profiles, so push updates use `broadcast_plugin_event("claimcoach", "<event>", payload)` (wire name `plugin.claimcoach.<event>`, received with `host.onEvent`). Request/response uses `ctx.rest`. |
| PC-5 | `plugin.yaml` uses `manifest_version: 2`, `requires_hermes: ">=0.22.5"`, `python_runtime: external` (the plugin manages its own interpreter; Hermes installs nothing), `provides_tools`, and `config_schema` (drives the Desktop settings form under `plugins.entries.claimcoach.settings`). |
| PC-6 | Durable state goes through `plugin_data_dir("claimcoach")` / `plugin_db("claimcoach")` (WAL SQLite) under the active profile home. The profile-independent root comes from `get_default_hermes_root()`. Nothing is stored in the install dir. |
| PC-7 | `transform_tool_result` is **fail-open**: if the hook raises, the original tool result is returned. It can't be the only safety guard. |
| PC-8 | Tools register with `ctx.register_tool(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, ...)`, and handlers return a JSON string. |

**Worker decision (follows from PC-4/PC-5):** heavy work (PDF rendering, vector search, model calls, background jobs) runs in an app-owned **worker** process, not in the gateway. The worker uses its own venv at `~/Models/.venvs/claimcoach` and listens on `127.0.0.1:18200` (the first port of the app's range) with a per-launch bearer token stored in the plugin data dir. `plugin_api.py` and the agent tools are thin, typed proxies to the worker, and the worker launches and stops the model servers.

## 8. Local models: reusing `~/Models`

ClaimCoach reads models from `MODELS_HOME` (default `~/Models`). It never copies weights, and it manages **its own** server processes on ports **18200–18219**.

| Step | Model | Tier | Runtime |
| --- | --- | --- | --- |
| EOB/letter page → structured text | `mlx-community/Qwen3-VL-8B-Instruct-4bit` | 8B | `~/Models/.venvs/mlx-vlm` → `mlx_vlm.server` |
| PHI span detection (+ regex validators for SSN/MRN/DOB/phone/member ID) | `mlx-community/Qwen3-8B-4bit` | 8B | `mlx_lm.server` |
| Denial-reason classification + appeal likelihood (JSON) | `Qwen3-8B` (later LoRA-tuned on de-identified outcomes) | 8B | `mlx_lm.server` |
| Corpus embeddings / rerank | `Qwen3-Embedding-8B-4bit-DWQ` / `Qwen3-Reranker-8B` (local MLX 4-bit) | 8B | `mlx-lm` venv |
| Plain-language explanation + checklist | `mlx-community/Qwen3-14B-4bit` | 14B | `mlx_lm.server` |
| Appeal letter drafting | `~/Models/Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` | 27B | `~/Models/.venvs/mtplx` → `mtplx serve` |
| Payer-call transcription (v1.1, batch) | `Voxtral-Small-24B-2507` 4-bit community MLX build | 24B | `mlx_audio.stt`, run alone after hours |

**Model manager requirements:** same pattern as the other apps, implemented independently:
- Per-role `models.yaml`: model dir under `MODELS_HOME`, venv, command, port.
- Lazy start, health check, idle unload.
- Memory guard (never two ≥ 14B models resident; Voxtral only when nothing else is loaded).
- Missing-model detection with confirmed `hf download` into `~/Models`.

**Budget:** interactive set (Qwen3-8B + embedding + reranker) ≈ 13.5 GB, plus VL-8B during extraction, Qwen3-14B for explanations, and Bonsai for drafting, loaded in sequence. Peak ≈ 22–28 GB.

## 9. Corpus: global and per user

ClaimCoach keeps **its own** corpus with two scopes:

| Scope | Contents | Location | Who writes |
| --- | --- | --- | --- |
| **global** (app-wide, every Hermes profile on this Mac) | CARC/RARC/group-code knowledge base, payer rule cards (timely-filing limits, appeal levels, required docs, addresses/fax), letter templates, de-identified example appeals | `<hermes root>/plugin-data/claimcoach/global/` (via `get_default_hermes_root()`) | Manager (settings page, `hermes claimcoach corpus import`) |
| **user** (one Hermes profile = one biller) | That biller's cases: source documents, extracted fields, drafts, outcomes, notes. **Contains PHI** | `plugin_data_dir("claimcoach")/user/` (follows the active profile) | The biller |

- **Retrieval:** explanations and drafts retrieve from `global` (rules, templates) plus the current case only. One case's PHI is never retrieved into another case's prompt.
- **Storage:** SQLite (`plugin_db`, WAL) + local vector index per scope. The `user` scope is **encrypted at rest**, with the key stored in the macOS Keychain.
- **Retention:** configurable auto-purge of source documents (default 90 days after case close). Outcomes are kept de-identified.
- **Manager view:** aggregates de-identified outcome stats across profiles, which requires those profiles to opt in. It never reads raw case documents.
- **Fine-tune export:** an explicit, manager-approved export of de-identified (redacted) case/outcome pairs to a file. It's never automatic.

## 10. Privacy, safety, compliance

- No case content leaves the Mac. Backend outbound calls are limited to user-confirmed model downloads and corpus imports.
- Logs, events, and agent tool results are redacted. Redactor recall is a release-blocking eval.
- Every draft is labeled "draft for human review". There's no send/submit button anywhere.
- HIPAA posture: ClaimCoach is local software and the practice remains the covered entity. Document safeguards (encryption, access via macOS account + Hermes profile, audit log of case access).
- Text extracted from uploaded documents is treated as data in every prompt (prompt-injection hardening).

## 11. Risks and open questions

| Risk / question | Mitigation / next step |
| --- | --- |
| LLM-based redaction misses PHI | Regex validators + second-pass check + synthetic PHI eval as a release gate |
| Payer rules change often | Rule cards carry source + "verified on" dates; stale cards are flagged in the UI |
| Labeled training/eval data | **Open:** source de-identified denial cases (partner billing service or synthetic generation by Bonsai, reviewed by a human) |
| Cloud Hermes chat model leaking PHI | §7.2 boundary + `transform_tool_result` guard + statusbar indicator |
| Memory pressure with other apps' models loaded | Memory guard + queueing |

## 12. Next workflow steps

1. **Specs**: `SPECS.md` in this folder, produced with the OhMyOrch `ingest-spec` contract (epics, user stories, Gherkin acceptance, source traceability) and checked with `ohmyorch validate-product-artifacts`.
2. **Plan**: OhMyOrch planning of `READY` stories into bounded changes, starting with the plugin skeleton + worker + model manager smoke test.
3. **Implement**: Claude Code agents deliver one story at a time. Review and test gates write evidence per §13 ES-5.

## 13. Engineering standards (Product Manager decision, 2026-10-30)

Decision recorded from the product owner: *"best code practices, standards and approaches ... use comments, tests evidences or runbooks, typings"*. These standards apply to every story. Stories cite the ES IDs.

| ID | Standard |
| --- | --- |
| ES-1 Typing | Python 3.12, type hints everywhere, `mypy --strict` clean. Every REST body, tool parameter/result, event payload, and config file is a Pydantic v2 model, and tool JSON schemas are generated from those models (one source of truth). `desktop/plugin.js` uses `// @ts-check` + JSDoc typedefs and passes `tsc --noEmit --checkJs` against a checked-in `types/hermes-plugin-sdk.d.ts` stub. |
| ES-2 Style | `ruff check` and `ruff format --check` clean for Python. `biome check` clean for JS. |
| ES-3 Comments | Google-style docstrings on every public module, class, and function. Comments explain *why*, not *what*. Each module docstring lists the story IDs (`US-x.y`) and rule IDs it implements, so a reader can trace criterion → code → test → evidence. |
| ES-4 Tests | `pytest` (+ `pytest-asyncio`, `httpx` ASGI transport) for Python and `node --test` with a fake `ctx`/`host` for `plugin.js`. Every Gherkin scenario maps to at least one automated test named `test_us_<epic>_<n>_<slug>`. Offline tests use a fake OpenAI-compatible model server. Tests that need real local models are marked `@pytest.mark.models`. Line coverage of the app package ≥ 85%. |
| ES-5 Evidence | Each delivered story writes `evidence/US-x.y/test-report.md` in OhMyOrch format (criterion quoted, `PASS`/`FAIL`/`UNVERIFIED`, command and actual output) plus JUnit XML, and eval JSON for model-quality stories. A criterion that wasn't exercised is `UNVERIFIED`, never `PASS`. |
| ES-6 Runbooks | `docs/runbooks/` covers install/enable, worker and model-server start/stop/health, model download/convert, corpus import/reindex/backup/restore, upgrade, and troubleshooting. Each runbook has **Preconditions, Steps (copy-paste commands), Verification, Rollback**. |
| ES-7 Quality gate | One command, `make check` (ruff, mypy, biome, tsc, offline pytest), must pass before a story goes to review. `pre-commit` runs the fast subset. |
| ES-8 Errors and logs | Every REST route returns either a typed success model or the error envelope `{"ok": false, "error": {"code", "message"}}`. No bare `except`. Logs are structured JSON with request/job IDs and never contain document text. |
| ES-9 Decisions | Architecture decisions are ADRs in `docs/adr/` (first: the worker decision in §7.9). |
