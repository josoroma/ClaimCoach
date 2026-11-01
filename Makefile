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
CALL ?=
FROM ?=
TO ?=
BACKUP_DIR ?= $(HOME)/ClaimCoach-backups
# Case targets (EPIC-5): CASE a case ID; FILE a local document; PROFILE as above; FIELD and VALUE
# a field path (payer_name, lines.0.service_date, …) and the value to confirm for it.
FIELD ?=
VALUE ?=
# Draft targets (EPIC-7): TEMPLATE a letter template ID (default: chosen by the denial reason);
# FORMAT pdf or docx; TO a file or folder to copy the export to (default: print where it is).
TEMPLATE ?=
FORMAT ?=
# Outcome targets (EPIC-8): OUTCOME overturned, upheld, or written_off; WEEK an ISO week such as
# 2026-W44 (default: the last completed week); MANAGER the approving manager's name (US-8.3).
OUTCOME ?=
WEEK ?=
MANAGER ?=
# Agent targets (EPIC-9): TOOL a claimcoach_* tool; ARGS its arguments as a JSON object (they go
# through the environment, never into shell text); CASE, for agent-denial, a case ID.
TOOL ?=
ARGS ?= {}
override ARGS := $(value ARGS)
export ARGS
# Through the environment, never spliced into shell text: a value may hold quotes.
# make expands an exported command-line value, so `$` in a manager's name would be lost; keep it.
override MANAGER := $(value MANAGER)
export FIELD VALUE TEMPLATE TO WEEK MANAGER
# Eval targets (EPIC-12): the eval sets (PHI_SET, DENIAL_SET; REVIEWS, the manager's draft reviews),
# where reports go (EVAL_OUT/US-12.x/), LIMIT cases of the denial set, EVAL_PROFILE the profile eval
# cases run in (default: PROFILE, else the active one), EVAL_CASE the denial-set case the egress
# check runs (default: the first with a PDF). Like the values above, they reach the command through
# the environment.
PHI_SET ?= tests/fixtures/phi/phi_set.json
DENIAL_SET ?= tests/fixtures/denials/denial_set.json
REVIEWS ?=
EVAL_OUT ?= evidence
LIMIT ?=
EVAL_PROFILE ?= $(PROFILE)
EVAL_CASE ?=
export PHI_SET DENIAL_SET REVIEWS EVAL_OUT LIMIT EVAL_PROFILE EVAL_CASE

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
MODEL_ROLES := extraction phi_detection classification embedding explanation drafting \
	transcription
REQUIRE_ROLE = $(if $(and $(filter 1,$(words $(ROLE))),$(filter $(ROLE),$(MODEL_ROLES))),:,\
	$(error usage: make $@ ROLE=<one of: $(MODEL_ROLES)>))
REQUIRE_CONFIRM = [ "$(CONFIRM)" = yes ] || { \
	echo "$@ fetches or writes model files under $(MODELS_HOME); re-run with CONFIRM=yes"; exit 2; }

# The corpus commands of `hermes claimcoach corpus`, run from this checkout (US-4.x). The ones that
# call the worker take CORPUS_PORT, so they reach it on WORKER_PORT like every other worker target.
CORPUS_CLI := $(UV) run python -m claimcoach.cli corpus
CORPUS_PORT = --port $(WORKER_PORT)
REQUIRE_SCOPE = $(if $(and $(filter 1,$(words $(SCOPE))),$(filter $(SCOPE),global user)),:,\
	$(error usage: make $@ SCOPE=<global|user> [PROFILE=<name>]))
REQUIRE_CORPUS_CONFIRM = [ "$(CONFIRM)" = yes ] || { \
	echo "$@ deletes or replaces corpus data and cannot be undone; re-run with CONFIRM=yes"; exit 2; }

# Case targets talk to the worker for one profile: PROFILE, or the active one.
CASE_PROFILE = $(or $(PROFILE),$(shell $(UV) run python -c \
	'from claimcoach.corpus.paths import active_profile; print(active_profile())'))
REQUIRE_CASE = [[ "$(CASE)" =~ ^[A-Za-z0-9_-]{1,64}$$ ]] || { \
	echo "usage: make $@ CASE=<case id>$(if $(filter case-add case-paste,$@), FILE=<document>)$(if \
	  $(filter case-call,$@), FILE=<recording>)$(if $(filter case-transcribe,$@), CALL=<call id>)"; exit 2; }
REQUIRE_CALL = [[ "$(CALL)" =~ ^call_[0-9a-f]{16}$$ ]] || { \
	echo "usage: make $@ CASE=<case id> CALL=<call id from make case-call>"; exit 2; }
REQUIRE_CASE_FILE = test -f "$(FILE)" || { \
	echo "usage: make $@ CASE=<case id> FILE=<$(if $(filter case-call,$@),recording,document)>"; exit 2; }
# TEMPLATE goes through the environment into JSON (the worker validates it); FORMAT is checked by
# make itself, before any shell sees it.
DRAFT_BODY = $(if $(TEMPLATE),-H 'Content-Type: application/json' --data-binary @<(python3 -c \
	'import json, os, sys; json.dump({"template_id": os.environ["TEMPLATE"]}, sys.stdout)'))
# filter treats % as a wildcard, so a value holding one is refused first.
REQUIRE_OUTCOME = $(if $(and $(filter 1,$(words $(OUTCOME))),$(if $(findstring %,$(OUTCOME)),,1),\
	$(filter $(OUTCOME),overturned upheld written_off)),:,\
	$(error usage: make $@ CASE=<case id> OUTCOME=<overturned|upheld|written_off>))
REQUIRE_FORMAT = $(if $(and $(filter 1,$(words $(FORMAT))),$(filter $(FORMAT),pdf docx)),:,\
	$(error usage: make $@ CASE=<case id> FORMAT=<pdf|docx> [TO=<file or folder>]))

# Start a case job ($(1): its route, extract, diagnose, draft, or correction, US-5.2, US-6.1,
# US-7.1, US-7.4; $(2): extra curl arguments, such as a JSON body; $(3): the job's kind when it is
# not the route's name: correct) and print its progress events until it ends; the target fails
# when the job ends `failed`, or when the case was already running a job of another kind (one job
# per case), which is followed instead and named on stderr.
# Backslash-newlines become spaces here, so every shell and Python statement ends with `;`.
CASE_JOB = started=$$($(WORKER_CURL) -X POST $(2) "$(WORKER_URL)/cases/$(CASE)/$(1)?profile=$(CASE_PROFILE)" \
	  | python3 -c 'import json, sys; b = json.load(sys.stdin); \
	    print(b["job_id"], b.get("kind", "extract")) if b.get("ok") \
	    else sys.exit("error: " + b["error"]["code"])') || exit 1; \
	read -r job kind <<< "$$started"; \
	[ "$$kind" = "$(or $(3),$(1))" ] || echo "a $$kind job is already running on this case; following it," \
	  "then run this target again" >&2; \
	after=0; while :; do \
	  body=$$($(WORKER_CURL) "$(WORKER_URL)/jobs/$$job/events?after=$$after&wait=20") || exit 1; \
	  out=$$(printf '%s' "$$body" | python3 -c 'import json, sys; b = json.load(sys.stdin); \
	    [print("%-11s %4.0f%%  %s" % (e["stage"], 100 * e["progress"], e.get("error_code") or ""), \
	      file=sys.stderr) for e in b["events"]]; \
	    last = b["events"][-1]["stage"] if b["events"] else ""; \
	    print(int(sys.argv[1]) + len(b["events"]), int(b["finished"]), last)' "$$after"); \
	  read -r after finished last <<< "$$out"; \
	  if [ "$$finished" = 1 ]; then [ "$$last" != failed ] && [ "$$kind" = "$(or $(3),$(1))" ]; exit; fi; \
	done

# The agent tools (US-9.1, US-9.2). TOOL is checked by make itself, before any shell sees it.
AGENT_TOOLS := claimcoach_explain_code claimcoach_payer_rules claimcoach_case_summary
AGENT_CLI := $(UV) run python -m claimcoach.agent
REQUIRE_TOOL = $(if $(and $(filter 1,$(words $(TOOL))),$(if $(findstring %,$(TOOL)),,1),\
	$(filter $(TOOL),$(AGENT_TOOLS))),:,\
	$(error usage: make $@ TOOL=<one of: $(AGENT_TOOLS)> ARGS='<JSON object>'))

# Story slug for test filters: US-3.1 -> us_3_1.
STORY_SLUG = $(shell echo '$(STORY)' | tr 'A-Z.-' 'a-z__')
REQUIRE_STORY = [[ "$(STORY)" =~ ^US-[0-9]+\.[0-9]+$$ ]] || { echo "usage: make $@ STORY=US-x.y"; exit 2; }

.PHONY: help doctor install check verify lint typecheck test test-py test-js test-story test-models \
        fmt coverage-html evidence evidence-check openspec-validate validate \
        plugin-link plugin-unlink plugin-enable plugin-disable plugin-install gateway-restart \
        start stop worker-venv worker-start worker-stop worker-status worker-health \
        models-init models-check models-status models-load models-unload models-download \
        redact phi-fixtures corpus-status corpus-import corpus-list corpus-reindex \
        corpus-purge corpus-audit corpus-backup corpus-restore corpus-key-export corpus-key-import \
        case-new case-list case-add case-paste case-show case-process case-confirm case-diagnose \
        case-draft case-edit case-export case-correct case-correction-export case-outcome \
        case-call case-transcribe transcription-queue \
        outcomes-summary outcomes-export \
        agent-tools agent-skill agent-call agent-denial agent-probe \
        eval-redaction eval-classification eval-drafts eval-latency eval-egress evals release-gate \
        clean

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Setup ---------------------------------------------------------------------------------------

doctor: ## Check tools, venvs, MODELS_HOME, the plugin link, and the worker (changes nothing)
	@ok=1; \
	for tool in $(UV) node $(NPM) $(OPENSPEC) $(HERMES) curl lsof; do \
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
	@$(CORPUS_CLI) status $(CORPUS_PORT)

corpus-import: ## Import a local bundle into the global scope: make corpus-import FILE=rules.yaml
	@test -f "$(FILE)" || { echo "usage: make corpus-import FILE=<bundle.yaml|.yml|.json>"; exit 2; }
	@$(CORPUS_CLI) import "$(FILE)" $(CORPUS_PORT)

corpus-list: ## List the global corpus with source, verified-on date, and the STALE flag
	@$(CORPUS_CLI) list $(CORPUS_PORT)

corpus-reindex: ## Re-embed a scope after a model change: make corpus-reindex SCOPE=global|user
	@$(REQUIRE_SCOPE)
	$(CORPUS_CLI) reindex --scope $(SCOPE) $(if $(PROFILE),--profile "$(PROFILE)") $(CORPUS_PORT)

corpus-purge: ## Retention purge now; one case: make corpus-purge PROFILE=p CASE=id CONFIRM=yes
	@if [ -n "$(CASE)" ]; then $(REQUIRE_CORPUS_CONFIRM); fi
	@$(CORPUS_CLI) purge $(if $(PROFILE),--profile "$(PROFILE)") \
	  $(if $(CASE),--case "$(CASE)" --confirm) $(CORPUS_PORT)

corpus-audit: ## Show the case-access audit log: make corpus-audit [PROFILE=p] [CASE=id]
	@$(CORPUS_CLI) audit $(if $(PROFILE),--profile "$(PROFILE)") $(if $(CASE),--case "$(CASE)") \
	  $(CORPUS_PORT)

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

# --- Cases (docs/runbooks/case-intake-extraction.md, case-diagnosis.md, appeal-drafting.md) -------
# These print case content (filenames, extracted fields) to this terminal only; nothing is logged.

case-new: ## Create an empty case and print its ID: make case-new [PROFILE=p]
	@$(WORKER_CURL) -X POST "$(WORKER_URL)/cases?profile=$(CASE_PROFILE)" | python3 -m json.tool

# IDs, dates, outcome, counts, and steps only (US-10.1): the pane's case list. Not audited.
case-list: ## List the profile's newest cases without case content: make case-list [PROFILE=p]
	@$(WORKER_CURL) "$(WORKER_URL)/cases?profile=$(CASE_PROFILE)" | python3 -m json.tool

case-add: ## Attach a PDF, PNG, JPEG, or text file: make case-add CASE=id FILE=eob.pdf
	@$(REQUIRE_CASE)
	@$(REQUIRE_CASE_FILE)
	@$(WORKER_CURL) -X POST -F "file=@\"$(FILE)\"" \
	  "$(WORKER_URL)/cases/$(CASE)/documents?profile=$(CASE_PROFILE)" | python3 -m json.tool

case-paste: ## Attach a text file's content as pasted text (835 or letter): make case-paste CASE=id FILE=era.835
	@$(REQUIRE_CASE)
	@$(REQUIRE_CASE_FILE)
	@$(WORKER_CURL) -X POST -H 'Content-Type: application/json' --data-binary @- \
	  "$(WORKER_URL)/cases/$(CASE)/paste?profile=$(CASE_PROFILE)" < <(python3 -c 'import json, sys; \
	    json.dump({"text": sys.stdin.read()}, sys.stdout)' < "$(FILE)") | python3 -m json.tool

case-show: ## Show a case with its source documents (audited case_opened): make case-show CASE=id
	@$(REQUIRE_CASE)
	@$(WORKER_CURL) "$(WORKER_URL)/cases/$(CASE)?profile=$(CASE_PROFILE)" | python3 -m json.tool

case-process: ## Extract a case and print its progress events until done: make case-process CASE=id
	@$(REQUIRE_CASE)
	@$(call CASE_JOB,extract)

case-diagnose: ## Diagnose an extracted case and print its progress events: make case-diagnose CASE=id
	@$(REQUIRE_CASE)
	@$(call CASE_JOB,diagnose)

case-confirm: ## Confirm a field's value: make case-confirm CASE=id FIELD=claim_id VALUE=CLAIM-77
	@$(REQUIRE_CASE)
	@[ -n "$$FIELD" ] && [ -n "$$VALUE" ] || { \
	  echo "usage: make $@ CASE=<case id> FIELD=<field path> VALUE=<value>"; exit 2; }
	@$(WORKER_CURL) -X POST -H 'Content-Type: application/json' --data-binary @- \
	  "$(WORKER_URL)/cases/$(CASE)/fields?profile=$(CASE_PROFILE)" < <(python3 -c 'import json, os, sys; \
	      json.dump({"path": os.environ["FIELD"], "value": os.environ["VALUE"]}, sys.stdout)') \
	  | python3 -m json.tool

case-draft: ## Draft a diagnosed case's appeal and print its progress: make case-draft CASE=id [TEMPLATE=t]
	@$(REQUIRE_CASE)
	@$(call CASE_JOB,draft,$(DRAFT_BODY))

case-edit: ## Save a text file as the case's draft (US-7.2): make case-edit CASE=id FILE=letter.txt
	@$(REQUIRE_CASE)
	@$(REQUIRE_CASE_FILE)
	@$(WORKER_CURL) -X POST -H 'Content-Type: application/json' --data-binary @- \
	  "$(WORKER_URL)/cases/$(CASE)/draft/text?profile=$(CASE_PROFILE)" < <(python3 -c 'import json, sys; \
	    json.dump({"text": sys.stdin.read()}, sys.stdout)' < "$(FILE)") | python3 -m json.tool

# The export is deleted 15 minutes after it is written, or when the worker stops (BR-6); TO copies
# it out first: created mode 0600, never over an existing file (TO goes through the environment).
# $(1): the export route under /cases/<case>; $(2): the exported file's name before -<case>.
define CASE_EXPORT
@if [ -n "$$TO" ]; then python3 -c 'import os, sys; target = os.environ["TO"]; \
  target = os.path.join(target, sys.argv[1]) if os.path.isdir(target) else target; \
  os.path.lexists(target) and sys.exit(f"{target} exists; choose another TO")' \
  "$(2)-$(CASE).$(FORMAT)" || exit 2; fi
@body=$$($(WORKER_CURL) -X POST -H 'Content-Type: application/json' -d '{"format": "$(FORMAT)"}' \
  "$(WORKER_URL)/cases/$(CASE)/$(1)?profile=$(CASE_PROFILE)") || { echo "$$body"; exit 1; }; \
printf '%s' "$$body" | python3 -m json.tool; \
if [ -n "$$TO" ]; then printf '%s' "$$body" | python3 -c 'import json, os, sys; \
  body = json.load(sys.stdin); target = os.environ["TO"]; \
  target = os.path.join(target, body["filename"]) if os.path.isdir(target) else target; \
  data = open(body["path"], "rb").read(); \
  fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) \
    if not os.path.lexists(target) else sys.exit(f"{target} exists; choose another TO"); \
  os.write(fd, data); os.close(fd); print("copied to", target)' || exit 1; fi
endef

case-export: ## Export the case's draft as PDF or DOCX: make case-export CASE=id FORMAT=pdf [TO=dir]
	@$(REQUIRE_CASE)
	@$(REQUIRE_FORMAT)
	$(call CASE_EXPORT,export,appeal-draft)

# --- Corrected claims (docs/runbooks/appeal-drafting.md, US-7.4) --------------------------------
# A list of the changes a corrected claim needs, for the biller to make in their billing system.

case-correct: ## Draft a diagnosed case's corrected claim and print its progress: make case-correct CASE=id
	@$(REQUIRE_CASE)
	@$(call CASE_JOB,correction,,correct)

case-correction-export: ## Export the corrected-claim draft: make case-correction-export CASE=id FORMAT=pdf [TO=dir]
	@$(REQUIRE_CASE)
	@$(REQUIRE_FORMAT)
	$(call CASE_EXPORT,correction/export,corrected-claim-draft)

# --- Payer calls (docs/runbooks/payer-call-transcription.md) -------------------------------------
# A recording is sealed into the case; the worker transcribes it in the profile's after-hours
# window (transcription_start_hour..transcription_end_hour), alone, with the local Voxtral server.

case-call: ## Attach a WAV, MP3, FLAC, or M4A payer-call recording: make case-call CASE=id FILE=call.wav
	@$(REQUIRE_CASE)
	@$(REQUIRE_CASE_FILE)
	@$(WORKER_CURL) -X POST -F "file=@\"$(FILE)\"" \
	  "$(WORKER_URL)/cases/$(CASE)/calls?profile=$(CASE_PROFILE)" | python3 -m json.tool

case-transcribe: ## Queue a call for after-hours transcription: make case-transcribe CASE=id CALL=call_id
	@$(REQUIRE_CASE)
	@$(REQUIRE_CALL)
	@$(WORKER_CURL) -X POST "$(WORKER_URL)/cases/$(CASE)/calls/$(CALL)/transcribe?profile=$(CASE_PROFILE)" \
	  | python3 -m json.tool

# IDs, states, windows, dates, and error codes only: no recording, transcript, or filename.
transcription-queue: ## List the transcription queue (no case content)
	@$(WORKER_CURL) "$(WORKER_URL)/transcriptions" | python3 -m json.tool

# --- Outcomes (docs/runbooks/outcomes-and-export.md) ---------------------------------------------

# OUTCOME is checked by make itself, before any shell sees it. Recording an outcome closes the
# case (US-8.1): it takes no new documents or edits, and its content is purged on schedule.
case-outcome: ## Record how a case ended, which closes it: make case-outcome CASE=id OUTCOME=upheld
	@$(REQUIRE_CASE)
	@$(REQUIRE_OUTCOME)
	@$(WORKER_CURL) -X POST -H 'Content-Type: application/json' -d '{"outcome": "$(OUTCOME)"}' \
	  "$(WORKER_URL)/cases/$(CASE)/outcome?profile=$(CASE_PROFILE)" | python3 -m json.tool

# De-identified counts of the profiles that share their outcomes (share_outcome_stats); no case
# content. WEEK is checked by its shape here and by the calendar in the worker.
outcomes-summary: ## The manager's weekly summary of shared outcomes: make outcomes-summary [WEEK=2026-W44]
	@[[ -z "$$WEEK" || "$$WEEK" =~ ^[0-9]{4}-W[0-9]{2}$$ ]] || { \
	  echo "usage: make $@ [WEEK=<ISO week, such as 2026-W44>]"; exit 2; }
	@$(WORKER_CURL) "$(WORKER_URL)/outcomes/summary$${WEEK:+?week=$$WEEK}" | python3 -m json.tool

# The export runs only with MANAGER and CONFIRM=yes typed on this command line (the manager's
# approval, US-8.3; a CONFIRM left in the shell's environment does not count); without them the
# worker answers export_not_approved and writes nothing. MANAGER goes through the environment into
# JSON, never into shell text; make reduces CONFIRM to yes or no. The file holds de-identified pairs only and stays
# until the manager deletes it.
outcomes-export: ## Manager-approved, de-identified fine-tune export: make outcomes-export MANAGER="Dana Lee" CONFIRM=yes
	@body=$$(python3 -c 'import json, os, sys; manager = os.environ.get("MANAGER", ""); \
	  approval = {"manager": manager, "approved": sys.argv[1] == "yes"}; \
	  json.dump({"approval": approval} if manager else {}, sys.stdout)' \
	  "$(if $(and $(filter command line,$(origin CONFIRM)),$(filter yes,$(CONFIRM))),yes,no)"); \
	$(WORKER_CURL) -X POST -H 'Content-Type: application/json' --data-binary "$$body" \
	  "$(WORKER_URL)/outcomes/export" | python3 -m json.tool

# --- Agent (docs/runbooks/agent-tools.md) ------------------------------------------------------

# What the Hermes agent gets: the guarded tool results, the playbook skill, and /denial. Each call
# runs the same guarded handler Hermes runs, against the worker on WORKER_PORT (US-9.1 to US-9.4).
agent-tools: ## List the agent tools with their parameter schemas, the skill, and /denial (offline)
	@$(AGENT_CLI) tools

agent-skill: ## Print the claimcoach:denial-triage playbook skill (offline)
	@$(AGENT_CLI) skill

agent-call: ## Call a tool as the agent does: make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197"}'
	@$(REQUIRE_TOOL)
	@$(AGENT_CLI) call "$(TOOL)" --args "$$ARGS" --port $(WORKER_PORT)

agent-denial: ## Run the /denial slash command: make agent-denial [CASE=id]
	@$(if $(CASE),$(REQUIRE_CASE))
	@$(AGENT_CLI) denial $(CASE) --port $(WORKER_PORT)

agent-probe: ## Load the plugin into the local Hermes Agent (throwaway home): tools, skill, /denial
	$(UV) run pytest -m hermes -p no:cacheprovider --no-cov \
	  tests/test_us_1_1_plugin_package.py tests/test_us_9_3_skill.py tests/test_us_9_4_denial_command.py

# --- Evals and release gates (docs/runbooks/evals-release-gates.md) ------------------------------
# Each eval drives the running worker (make start) and its real local models, then writes its JSON
# report under $(EVAL_OUT)/US-12.x/. Exit 0: the target is met; 1: it is missed and the release is
# blocked; 2: nothing was measured (worker down, models missing, a download running, a bad set).
# Eval cases are purged as soon as each flow ends.

EVAL_CLI := $(UV) run python -m claimcoach.evals
EVAL_ARGS = --out "$$EVAL_OUT" --port $(WORKER_PORT)
DENIAL_ARGS = $(EVAL_ARGS) --set "$$DENIAL_SET"
PROFILE_ARG = $${EVAL_PROFILE:+--profile "$$EVAL_PROFILE"}
LIMIT_ARG = $${LIMIT:+--limit "$$LIMIT"}
# What `make evals` runs. Without REVIEWS, eval-drafts is "not measured", which blocks the release:
# NFR-2 is never passed by default.
EVAL_GATES = eval-redaction eval-classification eval-drafts eval-latency eval-egress

eval-redaction: ## US-12.1 release gate: PHI recall >= 98% on the synthetic set, per category
	$(EVAL_CLI) redaction --set "$$PHI_SET" $(EVAL_ARGS)

eval-classification: ## US-12.2: denial classification accuracy >= 85% [LIMIT=n] [EVAL_PROFILE=p]
	$(EVAL_CLI) classification $(DENIAL_ARGS) $(PROFILE_ARG) $(LIMIT_ARG)

eval-drafts: ## US-12.2: drafts accepted with minor edits >= 70%: make eval-drafts REVIEWS=reviews.json
	@[ -n "$$REVIEWS" ] || { echo "not measured: make $@ REVIEWS=<the manager's draft reviews (JSON)>"; exit 2; }
	$(EVAL_CLI) drafts --reviews "$$REVIEWS" --out "$$EVAL_OUT"

eval-latency: ## US-12.3: median upload-to-draft <= 10 min on this Mac [LIMIT=n] [EVAL_PROFILE=p]
	$(EVAL_CLI) latency $(DENIAL_ARGS) $(PROFILE_ARG) $(LIMIT_ARG)

# The flow goes through the plugin_api router, which works in the active profile (HERMES_HOME).
eval-egress: ## US-12.4: one full case flow opens no non-loopback connection [EVAL_CASE=id]
	$(EVAL_CLI) egress $(DENIAL_ARGS) $${EVAL_CASE:+--case "$$EVAL_CASE"}

# Every gate runs even after one misses, so a release decision sees all of them at once.
evals: ## Run every eval gate against the running worker; fails when any is missed or not measured
	@failed=; for gate in $(EVAL_GATES); do \
	  echo "== $$gate"; $(MAKE) --no-print-directory "$$gate" || failed="$$failed $$gate"; \
	done; \
	if [ -n "$$failed" ]; then echo "release blocked by:$$failed"; exit 1; fi; \
	echo "every eval gate passed: $(EVAL_GATES)"

release-gate: ## The release decision: make verify (offline), then make evals (worker + real models)
	@$(MAKE) --no-print-directory verify
	@$(MAKE) --no-print-directory evals

clean: ## Remove caches and coverage output
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage .coverage.*
	find . -name __pycache__ -type d -prune -not -path './.venv/*' -not -path './node_modules/*' -exec rm -rf {} +
