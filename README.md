# ClaimCoach

Local-only denial-management coach for medical billers, shipped as one Hermes Desktop plugin
package. PHI never leaves the Mac. Product: [PRD.md](PRD.md). Backlog: [SPECS.md](SPECS.md).

## Layout

```text
plugin/                     # the Hermes package (symlinked to ~/.hermes/plugins/claimcoach)
├── plugin.yaml             # manifest v2; config_schema generated from ClaimCoachSettings
├── __init__.py             # agent half: register(ctx) → claimcoach_* tools
├── _bootstrap.py           # makes plugin/claimcoach importable as `claimcoach`
├── dashboard/              # backend half: manifest.json + plugin_api.py (router)
├── desktop/plugin.js       # desktop half (plain ESM, // @ts-check) + tests/ (node --test)
├── skills/denial-triage/
└── claimcoach/             # app package: api/, agent/, worker/, models/, settings.py, paths.py
tests/                      # pytest: test_us_<epic>_<n>_*.py, fakes/, hermes/ probe
tools/check_evidence.py     # evidence report contract
types/hermes-plugin-sdk.d.ts
docs/runbooks/ · docs/adr/  # ES-6, ES-9
evidence/US-x.y/            # ES-5 test reports + JUnit
openspec/                   # OpenSpec changes (one per story) and specs
.claude/                    # Claude Code harness: deliver-story skill, reviewer/tester agents, hooks
```

Heavy work runs in the worker (`127.0.0.1:18200`, per-launch token):
[ADR-0001](docs/adr/0001-worker-sidecar.md). The worker runs the local model servers from
`models.yaml` on `127.0.0.1:18201`–`18219`: started on first use, unloaded when idle, never two
≥14B models resident (EPIC-2). Weights are read in place from `MODELS_HOME` (`~/Models`).

## Develop

```bash
make install
```

```bash
make check
```

`make check` is the quality gate (ES-7): ruff, ruff format, biome, mypy `--strict`, tsc
`--checkJs`, offline pytest and `node --test`, each with 100% coverage. `make verify` also checks
the evidence and runs the gate's own self-tests. `make` lists every target.

Delivery flow per story: OpenSpec change (`openspec/changes/us-x-y-*`) → implementation and tests
→ `make check` → `make evidence STORY=US-x.y` + `evidence/US-x.y/test-report.md` →
`make evidence-check` → independent review → `openspec archive`. In Claude Code the
`deliver-story` skill (`.claude/skills/`) runs this flow; project hooks format Python on every
edit, keep `openspec/specs/` and archived changes immutable, and deny agents model downloads.

## Run

[docs/runbooks/install-enable.md](docs/runbooks/install-enable.md),
[docs/runbooks/worker-start-stop-health.md](docs/runbooks/worker-start-stop-health.md), and
[docs/runbooks/model-download-convert.md](docs/runbooks/model-download-convert.md).

```bash
make models-check
```

```bash
make models-status
```
