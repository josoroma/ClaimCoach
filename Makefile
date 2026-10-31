# ClaimCoach developer and operator commands. `make` lists them.
# ES-7: `make check` is the one quality gate every story passes before review.
.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

MODELS_HOME ?= $(HOME)/Models
HERMES_HOME ?= $(HOME)/.hermes
HERMES ?= hermes
UV ?= uv
NPM ?= npm
WORKER_VENV ?= $(MODELS_HOME)/.venvs/claimcoach
WORKER_PYTHON ?= $(WORKER_VENV)/bin/python
WORKER_PORT ?= 18200
PLUGIN_LINK ?= $(HERMES_HOME)/plugins/claimcoach
OPENSPEC ?= openspec
OHMYORCH ?= $(HOME)/sites/OhMyOrch/plugins/ohmyorch/bin/ohmyorch

# make check runs everything except real-model tests and the gate's own self-tests.
PYTEST_MARKERS ?= not models and not gate
# Extra files for mypy; the gate self-test injects a deliberately broken module here.
MYPY_EXTRA ?=
STORY ?=
# Model targets: ROLE is a models.yaml role; downloads and conversions also need CONFIRM=yes (BR-1).
ROLE ?=
CONFIRM ?=
# make redact: a local text file to send through the worker's PHI redactor; make corpus-import: a
# local YAML/JSON corpus bundle.
FILE ?=
# Corpus targets (EPIC-4): SCOPE is global or user; PROFILE a Hermes profile (default: the active
# one); CASE a case ID; FROM a backup folder or key file; TO a key file to create.
SCOPE ?=
PROFILE ?=
CASE ?=
FROM ?=
TO ?=
BACKUP_DIR ?= $(HOME)/ClaimCoach-backups

MYPY_FILES := plugin/claimcoach tests tools
# Entry points Hermes imports as package members; mypy checks them in a second pass.
ENTRY_POINTS := plugin/__init__.py plugin/_bootstrap.py plugin/dashboard/plugin_api.py

export MODELS_HOME HERMES_HOME

WORKER_URL := http://127.0.0.1:$(WORKER_PORT)
# curl to the worker with this launch's token. The header goes through a file descriptor so `ps`
# never shows the token, and proxies are bypassed so no proxy ever sees it. pipefail is set here
# because macOS ships GNU Make 3.81, which ignores .SHELLFLAGS: an error envelope piped through
# json.tool must still fail the target.
WORKER_CURL = set -o pipefail; token_file="$(HERMES_HOME)/plugin-data/claimcoach/worker/token"; \
	test -s "$$token_file" || { echo "no token at $$token_file; is the worker running?"; exit 1; }; \
	curl -sS --fail-with-body --noproxy '*' \
	  -H @<(printf 'Authorization: Bearer %s\n' "$$(cat "$$token_file")")
# ModelRole values. ROLE is checked by make itself, before any shell sees it.
MODEL_ROLES := extraction phi_detection classification embedding rerank explanation drafting \
	transcription
REQUIRE_ROLE = $(if $(and $(filter 1,$(words $(ROLE))),$(filter $(ROLE),$(MODEL_ROLES))),:,\
	$(error usage: make $@ ROLE=<one of: $(MODEL_ROLES)>))
REQUIRE_CONFIRM = [ "$(CONFIRM)" = yes ] || { \
	echo "$@ fetches or writes model files under $(MODELS_HOME); re-run with CONFIRM=yes"; exit 2; }

# The corpus commands of `hermes claimcoach corpus`, run from this checkout (US-4.x).
CORPUS_CLI := $(UV) run python -m claimcoach.cli corpus
REQUIRE_SCOPE = $(if $(and $(filter 1,$(words $(SCOPE))),$(filter $(SCOPE),global user)),:,\
	$(error usage: make $@ SCOPE=<global|user> [PROFILE=<name>]))
REQUIRE_CORPUS_CONFIRM = [ "$(CONFIRM)" = yes ] || { \
	echo "$@ deletes or replaces corpus data and cannot be undone; re-run with CONFIRM=yes"; exit 2; }

# Story slug for test filters: US-3.1 -> us_3_1.
STORY_SLUG = $(shell echo '$(STORY)' | tr 'A-Z.-' 'a-z__')
REQUIRE_STORY = [[ "$(STORY)" =~ ^US-[0-9]+\.[0-9]+$$ ]] || { echo "usage: make $@ STORY=US-x.y"; exit 2; }

.PHONY: help doctor install check verify lint typecheck test test-py test-js test-story test-models \
        fmt coverage-html evidence evidence-check openspec-validate validate \
        plugin-link plugin-unlink plugin-enable plugin-disable plugin-install gateway-restart \
        start stop worker-venv worker-start worker-stop worker-status worker-health \
        models-init models-check models-status models-load models-unload models-download \
        models-convert redact phi-fixtures corpus-status corpus-import corpus-list corpus-reindex \
        corpus-purge corpus-audit corpus-backup corpus-restore corpus-key-export corpus-key-import \
        clean

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Setup ---------------------------------------------------------------------------------------

doctor: ## Check tools, venvs, MODELS_HOME, the plugin link, and the worker (changes nothing)
	@ok=1; \
	for tool in $(UV) node $(NPM) $(OPENSPEC) $(HERMES) curl; do \
	  if command -v "$$tool" >/dev/null 2>&1; then printf '  ok       %s\n' "$$tool"; \
	  else printf '  missing  %s\n' "$$tool"; ok=0; fi; \
	done; \
	if [ -d "$(MODELS_HOME)" ]; then echo "  ok       MODELS_HOME=$(MODELS_HOME)"; \
	else echo "  missing  MODELS_HOME=$(MODELS_HOME)"; ok=0; fi; \
	if [ -x "$(WORKER_PYTHON)" ]; then echo "  ok       worker venv $(WORKER_VENV)"; \
	else echo "  missing  worker venv $(WORKER_VENV) (make worker-venv)"; fi; \
	if [ -L "$(PLUGIN_LINK)" ]; then echo "  ok       plugin link $(PLUGIN_LINK)"; \
	else echo "  missing  plugin link $(PLUGIN_LINK) (make plugin-link)"; fi; \
	if $(UV) run python -m claimcoach.worker.launcher status --port $(WORKER_PORT) >/dev/null 2>&1; \
	then echo "  ok       worker on $(WORKER_URL)"; else echo "  stopped  worker (make start)"; fi; \
	echo "Model roles (weights under MODELS_HOME):"; \
	$(UV) run python -m claimcoach.models check || ok=0; \
	[ "$$ok" = 1 ]

install: ## Install dev dependencies (uv + npm) and the pre-commit hook
	$(UV) sync --frozen
	$(NPM) ci --no-audit --no-fund
	$(UV) run pre-commit install

# --- Quality gate (ES-7) -------------------------------------------------------------------------

check: lint typecheck test ## The quality gate: lint, types, offline tests, 100% coverage

verify: check evidence-check ## check, evidence-check, then the gate's self-tests
	$(UV) run pytest -m gate -p no:cacheprovider

lint: ## ruff check, ruff format --check, biome check
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(NPM) exec --no -- biome check .

typecheck: ## mypy --strict (app, tests, tools, entry points) and tsc --checkJs
	$(UV) run mypy $(MYPY_FILES) $(MYPY_EXTRA)
	$(UV) run mypy --no-explicit-package-bases $(ENTRY_POINTS)
	$(NPM) exec --no -- tsc --noEmit -p tsconfig.json

test: test-py test-js ## Offline pytest and node --test, both with 100% coverage

test-py: ## Offline pytest with branch coverage (fails under 100%)
	$(UV) run pytest -m "$(PYTEST_MARKERS)" --cov --cov-report=term-missing

test-js: ## node --test for desktop/plugin.js with coverage (fails under 100%)
	$(NPM) test --silent

test-story: ## Offline tests of one story, no coverage gate: make test-story STORY=US-3.1
	@$(REQUIRE_STORY)
	$(UV) run pytest -m "$(PYTEST_MARKERS)" -p no:cacheprovider --no-cov -k "$(STORY_SLUG)"
	@if grep -qs "test_$(STORY_SLUG)_" plugin/desktop/tests/*.mjs; then \
	  node --import ./plugin/desktop/tests/register-fakes.mjs --test \
	    --test-name-pattern="$(STORY_SLUG)" plugin/desktop/tests/; \
	fi

test-models: ## Real-model tests (@pytest.mark.models); each skips when its weights are missing
	$(UV) run pytest -m models -p no:cacheprovider --no-cov -rs

fmt: ## Apply ruff and biome fixes and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .
	$(NPM) exec --no -- biome check --write .

coverage-html: ## HTML coverage report in htmlcov/
	$(UV) run pytest -m "$(PYTEST_MARKERS)" --cov --cov-report=html

# --- Delivery evidence (ES-5) --------------------------------------------------------------------

evidence: ## Record JUnit XML for one story: make evidence STORY=US-1.2
	@$(REQUIRE_STORY)
	@mkdir -p "evidence/$(STORY)"
	$(UV) run pytest -m "not models" -p no:cacheprovider --no-cov -k "$(STORY_SLUG)" \
	  --junitxml="evidence/$(STORY)/junit.xml" -o junit_suite_name="$(STORY)"
	@# US-1.4 owns the whole node suite; later stories record only their own node tests.
	@if [ "$(STORY)" = "US-1.4" ]; then pattern=; \
	elif grep -qs "test_$(STORY_SLUG)_" plugin/desktop/tests/*.mjs; then \
	  pattern="--test-name-pattern=$(STORY_SLUG)"; else exit 0; fi; \
	node --import ./plugin/desktop/tests/register-fakes.mjs --test $$pattern \
	  --test-reporter=junit --test-reporter-destination="evidence/$(STORY)/junit-node.xml" \
	  plugin/desktop/tests/

evidence-check: ## Validate every evidence/US-x.y report and JUnit file
	$(UV) run python tools/check_evidence.py evidence
	@if [ -x "$(OHMYORCH)" ]; then \
	  for r in evidence/US-*/test-report.md; do \
	    s=$$(basename "$$(dirname "$$r")"); \
	    "$(OHMYORCH)" --project-root "$(CURDIR)" validate-test-report --quiet --report "$$r" --story "$$s" \
	      || { echo "OhMyOrch rejected $$r"; exit 1; }; \
	  done; \
	else echo "OhMyOrch not found at $(OHMYORCH); skipped its validator"; fi

openspec-validate: ## Validate OpenSpec changes and specs (strict)
	$(OPENSPEC) validate --all --strict

validate: ## hermes plugins validate on the package
	$(HERMES) plugins validate plugin/

# --- Install / enable (docs/runbooks/install-enable.md) ------------------------------------------

plugin-link: ## Symlink plugin/ to ~/.hermes/plugins/claimcoach (dev install)
	@if [ -e "$(PLUGIN_LINK)" ] && [ ! -L "$(PLUGIN_LINK)" ]; then \
	  echo "$(PLUGIN_LINK) exists and is not a symlink; move it aside first"; exit 1; fi
	@mkdir -p "$(dir $(PLUGIN_LINK))"
	ln -sfn "$(CURDIR)/plugin" "$(PLUGIN_LINK)"

plugin-unlink: ## Remove the dev symlink (never a real directory)
	@if [ -L "$(PLUGIN_LINK)" ]; then rm "$(PLUGIN_LINK)"; else echo "no symlink at $(PLUGIN_LINK)"; fi

plugin-enable: ## Enable the Python half (restart the gateway afterwards)
	$(HERMES) plugins enable claimcoach

plugin-disable: ## Disable the Python half
	$(HERMES) plugins disable claimcoach

gateway-restart: ## Restart the Hermes gateway so it reloads plugin_api.py and the agent tools
	$(HERMES) gateway restart

plugin-install: plugin-link plugin-enable gateway-restart ## Dev install: link, enable, restart

# --- Day to day ----------------------------------------------------------------------------------

start: worker-start worker-health ## Start the worker and check its health

stop: worker-stop ## Stop the worker (it stops every model server it started)

# --- Worker (docs/runbooks/worker-start-stop-health.md) ------------------------------------------

worker-venv: ## Create the worker venv in $(WORKER_VENV) with Python 3.12
	$(UV) venv --python 3.12 "$(WORKER_VENV)"
	$(UV) pip install --python "$(WORKER_PYTHON)" -e "$(CURDIR)"

worker-start: ## Start the worker on 127.0.0.1:$(WORKER_PORT)
	$(UV) run python -m claimcoach.worker.launcher start --port $(WORKER_PORT) --python "$(WORKER_PYTHON)"

worker-stop: ## Stop the worker and remove its token
	$(UV) run python -m claimcoach.worker.launcher stop --port $(WORKER_PORT)

worker-status: ## Print the running worker's handle (exit 1 when stopped)
	$(UV) run python -m claimcoach.worker.launcher status --port $(WORKER_PORT)

worker-health: ## GET /health on the worker with the current token
	@$(WORKER_CURL) "$(WORKER_URL)/health"; echo

# --- Local models (docs/runbooks/model-download-convert.md, worker-start-stop-health.md) ---------

models-init: ## Write the default models.yaml to the data dir (never overwrites an edited one)
	$(UV) run python -m claimcoach.models init

models-check: ## Validate models.yaml and list each role's port, weights, and venv (offline)
	$(UV) run python -m claimcoach.models check

models-status: ## GET /models/status from the running worker
	@$(WORKER_CURL) "$(WORKER_URL)/models/status" | python3 -m json.tool

models-load: ## Start a role's model server and wait until healthy: make models-load ROLE=classification
	@$(REQUIRE_ROLE)
	@$(WORKER_CURL) -X POST "$(WORKER_URL)/models/$(ROLE)/load" | python3 -m json.tool

models-unload: ## Stop a role's model server now: make models-unload ROLE=classification
	@$(REQUIRE_ROLE)
	@$(WORKER_CURL) -X POST "$(WORKER_URL)/models/$(ROLE)/unload" | python3 -m json.tool

models-download: ## Download a role's model into MODELS_HOME: make models-download ROLE=x CONFIRM=yes
	@$(REQUIRE_ROLE)
	@$(REQUIRE_CONFIRM)
	@$(WORKER_CURL) -X POST -H 'Content-Type: application/json' \
	  -d '{"role": "$(ROLE)", "confirm": true}' "$(WORKER_URL)/models/download" | python3 -m json.tool

models-convert: override ROLE := $(or $(ROLE),rerank)
models-convert: ## Convert the reranker to local MLX 4-bit: make models-convert CONFIRM=yes
	@$(REQUIRE_ROLE)
	@$(REQUIRE_CONFIRM)
	@$(WORKER_CURL) -X POST -H 'Content-Type: application/json' \
	  -d '{"role": "$(ROLE)", "confirm": true}' "$(WORKER_URL)/models/convert" | python3 -m json.tool

# --- PHI redaction (docs/runbooks/phi-redaction.md) ----------------------------------------------

redact: ## Print a text file redacted by the running worker: make redact FILE=note.txt
	@test -f "$(FILE)" || { echo "usage: make redact FILE=<text file>"; exit 2; }
	@# The file goes to the worker on loopback via stdin (never argv); only redacted text or the
	@# error code is printed.
	@$(WORKER_CURL) -X POST -H 'Content-Type: application/json' --data-binary @- \
	  "$(WORKER_URL)/redact" < <(python3 -c 'import json, sys; \
	    json.dump({"text": sys.stdin.read()}, sys.stdout)' < "$(FILE)") \
	  | python3 -c 'import json, sys; b = json.load(sys.stdin); ok = b.get("ok") is True; \
	    print(b["text"]) if ok else print("error:", b["error"]["code"], file=sys.stderr); \
	    ok and print("counts:", json.dumps(b["counts"]), file=sys.stderr); sys.exit(0 if ok else 1)'

phi-fixtures: ## Regenerate the synthetic PHI fixture set (tests/fixtures/phi/phi_set.json)
	$(UV) run python -m tests.fixtures.phi.generate

# --- Corpus (docs/runbooks/corpus-import-reindex-backup-restore.md, phi-purge.md) ---------------

corpus-status: ## Show both corpus scopes: paths, counts, encryption, index embedding model
	@$(CORPUS_CLI) status

corpus-import: ## Import a local bundle into the global scope: make corpus-import FILE=rules.yaml
	@test -f "$(FILE)" || { echo "usage: make corpus-import FILE=<bundle.yaml|.yml|.json>"; exit 2; }
	@$(CORPUS_CLI) import "$(FILE)"

corpus-list: ## List the global corpus with source, verified-on date, and the STALE flag
	@$(CORPUS_CLI) list

corpus-reindex: ## Re-embed a scope after a model change: make corpus-reindex SCOPE=global|user
	@$(REQUIRE_SCOPE)
	$(CORPUS_CLI) reindex --scope $(SCOPE) $(if $(PROFILE),--profile "$(PROFILE)")

corpus-purge: ## Retention purge now; one case: make corpus-purge PROFILE=p CASE=id CONFIRM=yes
	@if [ -n "$(CASE)" ]; then $(REQUIRE_CORPUS_CONFIRM); fi
	@$(CORPUS_CLI) purge $(if $(PROFILE),--profile "$(PROFILE)") \
	  $(if $(CASE),--case "$(CASE)" --confirm)

corpus-audit: ## Show the case-access audit log: make corpus-audit [PROFILE=p] [CASE=id]
	@$(CORPUS_CLI) audit $(if $(PROFILE),--profile "$(PROFILE)") $(if $(CASE),--case "$(CASE)")

corpus-backup: ## Back up both scopes (online, encrypted as stored): make corpus-backup [BACKUP_DIR=d]
	@mkdir -p "$(BACKUP_DIR)" && chmod 700 "$(BACKUP_DIR)"
	@$(CORPUS_CLI) backup --to "$(BACKUP_DIR)"

corpus-restore: ## Replace the scopes from a backup (worker stopped): make corpus-restore FROM=d CONFIRM=yes
	@test -d "$(FROM)" || { echo "usage: make corpus-restore FROM=<backup folder> CONFIRM=yes"; exit 2; }
	@$(REQUIRE_CORPUS_CONFIRM)
	@$(CORPUS_CLI) restore --from "$(FROM)" --confirm

corpus-key-export: ## Write a profile's store key to a new 0600 file: make corpus-key-export TO=f [PROFILE=p]
	@test -n "$(TO)" || { echo "usage: make corpus-key-export TO=<new key file> [PROFILE=<name>]"; exit 2; }
	@$(CORPUS_CLI) key-export --to "$(TO)" $(if $(PROFILE),--profile "$(PROFILE)")

corpus-key-import: ## Put a backed-up key into the Keychain: make corpus-key-import FROM=f CONFIRM=yes
	@test -f "$(FROM)" || { echo "usage: make corpus-key-import FROM=<key file> CONFIRM=yes"; exit 2; }
	@$(REQUIRE_CORPUS_CONFIRM)
	@$(CORPUS_CLI) key-import --from "$(FROM)" --confirm $(if $(PROFILE),--profile "$(PROFILE)")

clean: ## Remove caches and coverage output
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage .coverage.*
	find . -name __pycache__ -type d -prune -not -path './.venv/*' -not -path './node_modules/*' -exec rm -rf {} +
