"""US-13.3 Data, API, Storage, and Upload Reference (README-DEV.md).

Scenarios: every gateway route is documented; every table is documented with its writers and
readers; uploads are documented with the limits the code enforces; every place ClaimCoach stores
data is documented. Each check reads the code itself (the router and request models, the schema of
a freshly opened store, the limits, and the path functions), so the guide fails ``make check``
when the code moves under it.
Rules: ES-8, BR-13, PRD §9.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import get_args

from fastapi.routing import APIRoute
from pydantic import BaseModel

from claimcoach import PLUGIN_NAME
from claimcoach.api.models import RetentionUpdate
from claimcoach.api.routes import router
from claimcoach.calls.queue import QUEUE_FILE
from claimcoach.calls.types import MAX_CALL_BYTES, AudioFormat
from claimcoach.cases.extraction import FieldConfirmation
from claimcoach.cases.models import (
    MAX_FILE_BYTES,
    MAX_PASTE_BYTES,
    CaseCreate,
    OutcomeRequest,
    PastedText,
)
from claimcoach.corpus.bundle import MAX_BUNDLE_BYTES, MAX_ITEMS
from claimcoach.corpus.paths import (
    DATABASE,
    INDEX,
    fine_tune_dir,
    global_scope_dir,
    profile_exports_dir,
    profile_user_scope_dir,
    transcription_dir,
)
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import CaseItemKind, CorpusScope
from claimcoach.egress import EGRESS_LOG
from claimcoach.letters.types import DraftEdit, DraftRequest, ExportRequest
from claimcoach.models.registry import REGISTRY_FILE
from claimcoach.models.types import DownloadRequest
from claimcoach.outcomes.export import APPROVALS_FILE
from claimcoach.outcomes.types import FineTuneExportRequest
from claimcoach.worker.config import WorkerConfig
from tests.doc_checks import code, section, table_rows
from tests.test_us_13_2_dev_guide import GUIDE

MIB = 1024 * 1024
_MULTIPART = {
    "/cases/{case_id}/documents",
    "/cases/{case_id}/calls",
    "/corpus/import/preview",
    "/corpus/import",
}
"""Routes whose body is one ``multipart/form-data`` part named ``file``."""

_REQUESTS: dict[str, type[BaseModel]] = {
    "/settings/retention": RetentionUpdate,
    "/models/download": DownloadRequest,
    "/cases": CaseCreate,
    "/cases/{case_id}/paste": PastedText,
    "/cases/{case_id}/calls/{call_id}/transcribe": CaseCreate,
    "/cases/{case_id}/process": CaseCreate,
    "/cases/{case_id}/fields": FieldConfirmation,
    "/cases/{case_id}/diagnose": CaseCreate,
    "/cases/{case_id}/draft": DraftRequest,
    "/cases/{case_id}/draft/text": DraftEdit,
    "/cases/{case_id}/export": ExportRequest,
    "/cases/{case_id}/correction": CaseCreate,
    "/cases/{case_id}/correction/export": ExportRequest,
    "/cases/{case_id}/outcome": OutcomeRequest,
    "/outcomes/export": FineTuneExportRequest,
}
"""The request model each JSON-body route reads; its example in the guide must validate."""


def _guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _gateway_routes() -> dict[tuple[str, str], str]:
    return {
        (method, route.path): route.response_model.__name__
        for route in router.routes
        if isinstance(route, APIRoute) and route.response_model is not None
        for method in route.methods or ()
    }


def _schema(tmp_path: Path) -> dict[str, set[str]]:
    """Every table a freshly opened store has: ``main.x`` / ``idx.x`` → its column names."""
    CorpusStore(tmp_path, CorpusScope.GLOBAL, embedding_model_id="guide-check").close()
    tables: dict[str, set[str]] = {}
    for schema, file in (("main", DATABASE), ("idx", INDEX)):
        db = sqlite3.connect(tmp_path / file)
        try:
            names = db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for (name,) in names:
                columns = db.execute(f"PRAGMA table_info({name})").fetchall()
                tables[f"{schema}.{name}"] = {column[1] for column in columns}
        finally:
            db.close()
    return tables


def _documented_columns(cell: str) -> set[str]:
    """The column names of a Columns cell; a parenthesized note (``kind`` values) is skipped."""
    return set(re.findall(r"`([^`]+)`", re.sub(r"\([^)]*\)", "", cell)))


# --- Scenario: Every gateway route is documented ---
def test_us_13_3_routes_documented() -> None:
    gateway = _gateway_routes()
    assert len(gateway) == len(router.routes), "every route has a response model"
    rows = {
        (row[0], code(row[1])): row
        for row in table_rows(section(_guide(), "REST API"))
        if row[0] in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }
    assert set(rows) == set(gateway), "the guide lists exactly the gateway's routes"
    for key, model in gateway.items():
        method, path = key
        _, _, request, response = rows[key]
        assert code(response) == model, f"{key}: response model differs"
        if method == "GET":
            assert request == "—" or request.startswith("query"), f"{key}: a GET has no body"
        elif path in _MULTIPART:
            assert "multipart `file`" in request, f"{key}: say it is a multipart upload"
        else:
            assert path in _REQUESTS, f"{key}: add its request model to this test"
            _REQUESTS[path].model_validate(json.loads(code(request)))
    assert '{"ok": false, "error": {"code": "...", "message": "..."}}' in _guide()


# --- Scenario: Every table is documented with its writers and readers ---
def test_us_13_3_tables_documented(tmp_path: Path) -> None:
    tables = _schema(tmp_path)
    assert {"main.cases", "main.case_items", "idx.vectors"} <= set(tables)
    rows = {
        code(row[0]): row
        for row in table_rows(section(_guide(), "Database schema"))
        if row[0].startswith("`")
    }
    assert set(rows) == set(tables), "the guide lists exactly the store's tables"
    for name, columns in tables.items():
        _, documented, written_by, read_by, phi = rows[name]
        assert _documented_columns(documented) == columns, f"{name}: columns differ"
        assert len(written_by) > 10, f"{name}: say what writes it"
        assert len(read_by) > 10, f"{name}: say what reads it"
        assert re.search(r"\b(Yes|No)\b", phi), f"{name}: say whether it holds PHI"
    kinds = re.search(r"\(([^)]*)\)", rows["main.case_items"][1])
    assert kinds, "case_items lists its kinds"
    assert set(re.findall(r"`([^`]+)`", kinds.group(1))) == set(get_args(CaseItemKind))


def test_us_13_3_column_parser_skips_notes() -> None:
    assert _documented_columns("`a`, `kind` (`x`, `y`), `b` (note)") == {"a", "kind", "b"}


# --- Scenario: Uploads are documented with the limits the code enforces ---
def test_us_13_3_upload_limits_match_code() -> None:
    rows = {row[0]: row for row in table_rows(section(_guide(), "Uploads"))}
    expected = {
        "Denial document": (MAX_FILE_BYTES, "/cases/{case_id}/documents"),
        "Pasted text": (MAX_PASTE_BYTES, "/cases/{case_id}/paste"),
        "Payer-call recording": (MAX_CALL_BYTES, "/cases/{case_id}/calls"),
        "Corpus bundle": (MAX_BUNDLE_BYTES, "/corpus/import/preview"),
    }
    assert set(rows) == set(expected)
    paths = {route.path for route in router.routes if isinstance(route, APIRoute)}
    for name, (limit, path) in expected.items():
        _, route, accepted, documented_limit, stored = rows[name]
        assert limit % MIB == 0
        assert documented_limit == f"{limit // MIB} MiB", f"{name}: limit differs from the code"
        assert path in route, f"{name}: route"
        assert path in paths
        assert accepted, f"{name}: say what it accepts"
        assert stored, f"{name}: say where it goes"
    for audio in get_args(AudioFormat):
        assert audio.upper() in rows["Payer-call recording"][2], f"{audio} not documented"
    assert f"up to {MAX_ITEMS} items" in rows["Corpus bundle"][2]
    uploads = section(_guide(), "Uploads")
    assert '`{"text": "..."}`' in uploads, "paste is a JSON body"
    assert "`.yaml`, `.yml`, or `.json`" in uploads, "a bundle is chosen by its file name"


# --- Scenario: Every place ClaimCoach stores data is documented ---
def test_us_13_3_storage_documented(tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    profile = root / "profiles" / "p"
    data = root / "plugin-data" / PLUGIN_NAME
    rows = [row for row in table_rows(section(_guide(), "Corpus and storage")) if len(row) == 5]

    def resolved(cell: str) -> Path:
        text = (
            code(cell).replace("<hermes root>", str(root)).replace("<profile home>", str(profile))
        )
        return Path(text)

    by_path = {resolved(row[1]): row for row in rows if "<" in code(row[1])}
    worker = WorkerConfig(data_dir=data)
    expected = {
        global_scope_dir(root, create=False): (DATABASE, INDEX),
        profile_user_scope_dir("p", root, create=False): (DATABASE, INDEX),
        profile_exports_dir("p", root): (),
        fine_tune_dir(root): (APPROVALS_FILE,),
        transcription_dir(root): (QUEUE_FILE,),
        worker.state_dir: (
            worker.token_path.name,
            worker.pid_path.name,
            worker.log_path.name,
            EGRESS_LOG,
        ),
        data / REGISTRY_FILE: (),
        data / "models": ("servers.json", "server-logs/"),
    }
    for path, files in expected.items():
        assert path in by_path, f"{path.relative_to(tmp_path)} is not documented where it lives"
        for name in files:
            assert name in by_path[path][2], f"{name} is not documented under {path.name}"
    for row in rows:
        assert row[3].split()[0].rstrip(",") in {"Yes", "No"}, f"{row[0]}: say if it holds PHI"
        assert row[4], f"{row[0]}: say how it is protected"
    phi = {row[0] for row in rows if row[3].startswith("Yes")}
    assert {"User scope", "Exports", "Transcription temp file"} <= phi
    assert "Keychain" in section(_guide(), "Corpus and storage")
