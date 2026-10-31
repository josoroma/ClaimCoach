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

.PHONY: help install check verify lint typecheck test test-py test-js fmt coverage-html \
        evidence evidence-check openspec-validate validate \
        plugin-link plugin-unlink plugin-enable plugin-disable \
        worker-venv worker-start worker-stop worker-status worker-health \
        models-init models-check models-status models-load models-unload models-download \
        models-convert clean

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Setup ---------------------------------------------------------------------------------------

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

fmt: ## Apply ruff and biome fixes and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .
	$(NPM) exec --no -- biome check --write .

coverage-html: ## HTML coverage report in htmlcov/
	$(UV) run pytest -m "$(PYTEST_MARKERS)" --cov --cov-report=html

# --- Delivery evidence (ES-5) --------------------------------------------------------------------

evidence: ## Record JUnit XML for one story: make evidence STORY=US-1.2
	@test -n "$(STORY)" || { echo "usage: make evidence STORY=US-x.y"; exit 2; }
	@mkdir -p "evidence/$(STORY)"
	$(UV) run pytest -m "not models" -p no:cacheprovider \
	  -k "$$(echo '$(STORY)' | tr 'A-Z.-' 'a-z__')" \
	  --junitxml="evidence/$(STORY)/junit.xml" -o junit_suite_name="$(STORY)"
	@if [ "$(STORY)" = "US-1.4" ]; then \
	  node --import ./plugin/desktop/tests/register-fakes.mjs --test \
	    --test-reporter=junit --test-reporter-destination="evidence/$(STORY)/junit-node.xml" \
	    plugin/desktop/tests/; \
	fi

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

clean: ## Remove caches and coverage output
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage .coverage.*
	find . -name __pycache__ -type d -prune -not -path './.venv/*' -not -path './node_modules/*' -exec rm -rf {} +
