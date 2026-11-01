# Proposal: US-13.2 Developer Guide: Models, Install, Configuration, First Run, and Daily Start

## Why

Setting ClaimCoach up meant reading six runbooks, the Makefile, and `models.yaml`. One page should take a developer from a clean Mac to a working pane, then to the everyday start, and say which model each role uses and why (SPECS.md US-13.2).

## What Changes

- `README-DEV.md` sections **Models** (every role: folder, source, venv, port, tier, use), **Install (first run)** (nine steps, each a `make` target or a Hermes step), **Start (every day)**, and **Configuration** (plugin settings, `models.yaml`, Make variables and environment), led by the shared logo.
- `tests/test_us_13_2_dev_guide.py`: the guide is checked against `models.default.yaml`, the Makefile's targets and variables, and `plugin.yaml`'s `config_schema`, so a drift fails `make check`. Its helpers (`section`, `table_rows`, `code`, `commands`) are shared with US-13.3 to US-13.5.

## Capabilities

### New Capabilities
- `dev-guide`: the developer guide's setup sections and their drift checks.

### Modified Capabilities
- None.

## Impact

- Docs and tests only. The engineering parts of the old README (layout, develop, release) move to README-DEV.md's Develop section.
