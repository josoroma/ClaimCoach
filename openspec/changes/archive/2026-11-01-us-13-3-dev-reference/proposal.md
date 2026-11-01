# Proposal: US-13.3 Data, API, Storage, and Upload Reference

## Why

To change a flow, a developer had to read `api/routes.py`, `corpus/store.py`, and the path modules to learn what each route takes and answers, what writes and reads each table, and where data lands on disk (SPECS.md US-13.3).

## What Changes

- `README-DEV.md` sections **REST API** (every gateway route: method, path, request, response model; the error envelope; worker-only routes; agent tools), **Database schema** (every table with its columns, writers, readers, and PHI), **Corpus and storage** (every folder and file with what it holds, PHI, and protection), and **Uploads** (route, accepted types, limit, where it goes, and how the body travels).
- `tests/test_us_13_3_reference.py`: routes from `router.routes`, tables and columns from `_SCHEMA`, limits from the code's constants, and file and folder names from the path modules.

## Capabilities

### New Capabilities
- `dev-reference`: the API, schema, storage, and upload reference and its drift checks.

### Modified Capabilities
- None.

## Impact

- Docs and tests only. Writing it surfaced that no pipeline step writes the user scope's `documents` and `chunks` tables yet (case content lives in `case_items`); the guide says so.
