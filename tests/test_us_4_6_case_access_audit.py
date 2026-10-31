"""US-4.6 Audit Log of Case Access.

Scenarios: opening a case writes an audit entry; audit entries cannot be changed. Also: every
case-level action is audited, entries carry no PHI, a purge keeps them, and the audit route.
Rules: BR-14, PRD §10.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claimcoach.corpus.paths import DATABASE
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseOutcome, PurgeRequest
from tests.fakes.corpus import add_case_document, corpus_client, make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> CorpusService:
    return make_service(tmp_path, corpus_server)


# --- Scenario: Opening a case writes an audit entry ---------------------------------------------


def test_us_4_6_opening_case_writes_audit_entry(service: CorpusService) -> None:
    store = service.user_store("biller-a", create=True)
    store.create_case("case-1")
    before = store.audit_log("case-1")
    record = store.open_case("case-1")
    assert record.case_id == "case-1"
    after = store.audit_log("case-1")
    assert len(after) == len(before) + 1
    entry = after[-1]
    assert (entry.action, entry.case_id, entry.profile) == (
        AuditAction.CASE_OPENED,
        "case-1",
        "biller-a",
    )
    assert entry.at >= before[-1].at
    assert entry.seq > before[-1].seq


def test_us_4_6_every_case_action_audited_without_phi(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    add_case_document(store, "case-1", PHI_DOCUMENTS[0]["text"], closed_days_ago=1)
    store.open_case("case-1")
    store.record_outcome("case-1", CaseOutcome.UPHELD)
    service.purge(PurgeRequest(profile="default", case_id="case-1", confirm=True))
    store.create_case("case-2")
    actions = [entry.action for entry in store.audit_log("case-1")]
    assert actions == [
        AuditAction.CASE_CREATED,
        AuditAction.DOCUMENT_ADDED,
        AuditAction.CASE_CLOSED,
        AuditAction.CASE_OPENED,
        AuditAction.OUTCOME_RECORDED,
        AuditAction.CASE_PURGED_ON_REQUEST,  # a confirmed manual purge, not the policy
    ]
    everything = store.audit_log()
    assert [entry.case_id for entry in everything][-1] == "case-2"
    dumped = "\n".join(entry.model_dump_json() for entry in everything)
    assert leaked_strings(dumped, PHI_DOCUMENTS[0]) == []


# --- Scenario: Audit entries cannot be changed --------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET action = 'case_created'",
        "DELETE FROM audit_log",
        "INSERT OR REPLACE INTO audit_log VALUES (1, '2026-01-01', 'case_created', 'x', 'p')",
        "REPLACE INTO audit_log VALUES (2, '2026-01-01', 'case_created', 'x', 'p')",
    ],
)
def test_us_4_6_audit_log_append_only(service: CorpusService, statement: str) -> None:
    store = service.user_store("default", create=True)
    store.create_case("case-1")
    store.open_case("case-1")
    entries = store.audit_log()
    with (
        sqlite3.connect(store.directory / DATABASE) as raw,
        pytest.raises(sqlite3.DatabaseError, match="append-only"),
    ):
        raw.execute(statement)
    assert store.audit_log() == entries


# --- The audit route ----------------------------------------------------------------------------


async def test_us_4_6_audit_route(service: CorpusService) -> None:
    store = service.user_store("biller-b", create=True)
    store.create_case("case-9")
    store.create_case("case-10")
    store.open_case("case-9")
    with corpus_client(service) as (client, _):
        one = await client.corpus_audit("biller-b", "case-9")
        everything = await client.corpus_audit("biller-b")
    assert [e.action for e in one.entries] == [AuditAction.CASE_CREATED, AuditAction.CASE_OPENED]
    assert {e.case_id for e in everything.entries} == {"case-9", "case-10"}
