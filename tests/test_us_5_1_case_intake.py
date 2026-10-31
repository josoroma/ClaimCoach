"""US-5.1 Create a Case and Add Documents (Python half).

Scenarios: a PDF or image is attached to a new case; pasted 835 text is attached to a case. Also:
the kind comes from the bytes, the upload parser refuses malformed bodies, refusals store nothing,
attached files are encrypted at rest and purged with the case, and the gateway only proxies. The
pane scenarios run under ``node --test`` (``plugin/desktop/tests/case_intake.test.mjs``).
Rules: ES-1, ES-8, BR-2, BR-6, BR-7, BR-13, BR-14, PC-4.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope
from claimcoach.cases.errors import (
    DocumentTooLargeError,
    MalformedUploadError,
    UnsupportedDocumentError,
)
from claimcoach.cases.intake import (
    is_edi_835,
    parse_upload,
    read_limited,
    sniff,
)
from claimcoach.cases.models import MAX_FILE_BYTES, MAX_PASTE_BYTES, Case, DocumentAdded
from claimcoach.corpus.errors import CaseNotFoundError
from claimcoach.corpus.paths import DATABASE
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseItem, PurgeRequest, utc_now
from claimcoach.events import CASE_ID_PATTERN
from tests.fakes.corpus import corpus_client, make_service
from tests.fakes.fake_model_server import FakeModelServer

PREFIX: Final = "/api/plugins/claimcoach"
PDF: Final = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
PNG: Final = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(64))
JPEG: Final = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(range(64))
PATIENT_FILENAME: Final = "Doe_Jane_EOB.pdf"
"""A filename that is PHI: it may be stored (encrypted) and shown in the pane, never logged."""

ERA_835: Final = (
    "ISA*00*          *00*          *ZZ*PAYERID        *ZZ*PROVIDERID     *261015*1200*^*00501*"
    "000000001*0*P*:~GS*HP*PAYERID*PROVIDERID*20261015*1200*1*X*005010X221A1~"
    "ST*835*0001~BPR*I*0*C*NON************20261015~TRN*1*12345*1512345678~"
    "N1*PR*ACME HEALTH PLAN~N1*PE*SYNTHETIC CLINIC*XX*1234567893~"
    "CLP*PCN-0001*4*250*0**12*CLAIM-77*11*1~NM1*QC*1*PATIENT*SYNTHETIC~"
    "SVC*HC:99213*250*0**1~DTM*472*20260901~CAS*CO*197*250~LQ*HE*N286~"
    "SE*12*0001~GE*1*1~IEA*1*000000001~"
)
"""A synthetic, PHI-free 835: one denied claim line (CO-197, remark N286)."""


def hermes_multipart(
    filename: str = "eob.pdf", content_type: str = "application/pdf", data: bytes = PDF
) -> tuple[bytes, str]:
    """Build the body exactly as Hermes' ``multipartBody`` does for a ``ctx.rest`` upload."""
    boundary = "----hermes-0123456789abcdef01234567"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + data
    body += f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(service: CorpusService) -> Iterator[tuple[WorkerClient, FastAPI]]:
    with corpus_client(service) as pair:
        yield pair


@pytest.fixture
def gateway(
    worker: tuple[WorkerClient, FastAPI], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    """The gateway router as Hermes mounts it, with the default profile active."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    app.dependency_overrides[routes.get_worker_client] = lambda: worker[0]
    return app


@pytest.fixture
async def desktop(gateway: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest``: the desktop half's calls to the gateway."""
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        yield client


async def new_case(desktop: httpx.AsyncClient) -> str:
    response = await desktop.post(f"{PREFIX}/cases", json={})
    assert response.status_code == 200, response.text
    return Case.model_validate_json(response.content).case_id


async def upload(
    desktop: httpx.AsyncClient, case_id: str, body: bytes, content_type: str
) -> httpx.Response:
    return await desktop.post(
        f"{PREFIX}/cases/{case_id}/documents", content=body, headers={"content-type": content_type}
    )


async def documents(desktop: httpx.AsyncClient, case_id: str) -> list[dict[str, Any]]:
    response = await desktop.get(f"{PREFIX}/cases/{case_id}")
    assert response.status_code == 200, response.text
    return [d.model_dump() for d in Case.model_validate_json(response.content).documents]


def assert_envelope(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = ErrorEnvelope.model_validate_json(response.content)
    assert (body.error.code, body.error.message) == (code, ERROR_MESSAGES[body.error.code])


def raw_database(service: CorpusService, profile: str = "default") -> bytes:
    directory = service.user_store(profile).directory
    return b"".join(path.read_bytes() for path in directory.iterdir() if path.is_file())


# --- Scenario: A PDF or image is attached to a new case -----------------------------------------


@pytest.mark.parametrize(
    "sample",
    [
        (PATIENT_FILENAME, "application/pdf", PDF, "pdf"),
        ("scan.png", "image/png", PNG, "image"),
        ("photo.jpg", "image/jpeg", JPEG, "image"),
    ],
    ids=["pdf", "png", "jpeg"],
)
async def test_us_5_1_pdf_or_image_attached(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    sample: tuple[str, str, bytes, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    filename, content_type, data, kind = sample
    caplog.set_level(logging.DEBUG)
    case_id = await new_case(desktop)
    assert re.fullmatch(CASE_ID_PATTERN, case_id)
    assert await documents(desktop, case_id) == []

    response = await upload(desktop, case_id, *hermes_multipart(filename, content_type, data))
    assert response.status_code == 200, response.text
    added = DocumentAdded.model_validate_json(response.content)
    assert (added.case_id, added.document.kind) == (case_id, kind)

    listed = await documents(desktop, case_id)
    assert len(listed) == 1
    assert listed[0] | {"added_at": None} == {
        "doc_id": added.document.doc_id,
        "kind": kind,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(data),
        "added_at": None,
    }
    # Stored encrypted (BR-6): neither the bytes nor the filename are on disk in the clear.
    store = service.user_store("default")
    assert store.case_item_data(case_id, added.document.doc_id) == data
    disk = raw_database(service)
    assert data[:24] not in disk
    assert filename.encode() not in disk
    assert filename not in caplog.text  # BR-14
    actions = [entry.action for entry in store.audit_log(case_id)]
    assert actions[:2] == [AuditAction.CASE_CREATED, AuditAction.CASE_OPENED]
    assert AuditAction.DOCUMENT_ADDED in actions


async def test_us_5_1_documents_accumulate_in_one_case(desktop: httpx.AsyncClient) -> None:
    case_id = await new_case(desktop)
    for body in (hermes_multipart(), hermes_multipart("letter.png", "image/png", PNG)):
        assert (await upload(desktop, case_id, *body)).status_code == 200
    listed = await documents(desktop, case_id)
    assert [d["kind"] for d in listed] == ["pdf", "image"]
    assert len({d["doc_id"] for d in listed}) == 2


async def test_us_5_1_httpx_multipart_is_accepted(desktop: httpx.AsyncClient) -> None:
    """Any well-formed single-file form works, not only Hermes' own encoder."""
    case_id = await new_case(desktop)
    response = await desktop.post(
        f"{PREFIX}/cases/{case_id}/documents", files={"file": ("eob.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 200, response.text
    assert DocumentAdded.model_validate_json(response.content).document.kind == "pdf"


async def test_us_5_1_case_lives_in_the_active_profile(
    tmp_path: Path, service: CorpusService, gateway: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes" / "profiles" / "biller-a"))
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        case_id = await new_case(desktop)
    assert service.user_store("biller-a").open_case(case_id).case_id == case_id
    scope = tmp_path / "hermes" / "profiles" / "biller-a" / "plugin-data" / "claimcoach" / "user"
    assert (scope / DATABASE).is_file()
    assert not (tmp_path / "hermes" / "plugin-data" / "claimcoach" / "user" / DATABASE).exists()


# --- Scenario: Pasted 835 text is attached to a case --------------------------------------------


async def test_us_5_1_pasted_835_attached(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await new_case(desktop)
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": ERA_835})
    assert response.status_code == 200, response.text
    added = DocumentAdded.model_validate_json(response.content)
    assert (added.document.kind, added.document.filename) == ("edi_835", None)
    assert added.document.content_type == "text/plain; charset=utf-8"

    listed = await documents(desktop, case_id)
    assert [(d["doc_id"], d["kind"]) for d in listed] == [(added.document.doc_id, "edi_835")]
    stored = service.user_store("default").case_item_data(case_id, added.document.doc_id)
    assert stored == ERA_835.encode()


async def test_us_5_1_pasted_letter_is_text(desktop: httpx.AsyncClient) -> None:
    case_id = await new_case(desktop)
    letter = "Dear provider,\nThe claim was denied: CO-197, precertification absent.\n"
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": letter})
    assert DocumentAdded.model_validate_json(response.content).document.kind == "text"


# --- The kind comes from the bytes ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (PDF, "pdf"),
        (PNG, "image"),
        (JPEG, "image"),
        (ERA_835.encode(), "edi_835"),
        (("\ufeff\r\n" + ERA_835).encode(), "edi_835"),
        (ERA_835.replace("*", "|").replace("~", "\n").encode(), "edi_835"),
        (b"Denial letter: CO-197", "text"),
        (ERA_835.replace("ST*835", "ST*837").encode(), "text"),
        (b"ISA*00*short~ST*835~", "text"),
    ],
    ids=["pdf", "png", "jpeg", "835", "835-bom", "835-other-delims", "letter", "837", "short-isa"],
)
def test_us_5_1_sniffs_kind_from_bytes(data: bytes, kind: str) -> None:
    assert sniff(data) == kind


@pytest.mark.parametrize(
    "data", [b"\x00\x01\x02\xff\xfe", b"   \n\t ", b"text\x00with nul", b"GIF89a\x01\x00"]
)
def test_us_5_1_unsupported_bytes_refused(data: bytes) -> None:
    with pytest.raises(UnsupportedDocumentError):
        sniff(data)


def test_us_5_1_declared_type_is_display_only() -> None:
    body, content_type = hermes_multipart("eob.pdf", "application/pdf", PNG)
    upload_file = parse_upload(body, content_type)
    assert (upload_file.content_type, sniff(upload_file.data)) == ("application/pdf", "image")


def test_us_5_1_is_edi_835_needs_an_isa_segment() -> None:
    assert not is_edi_835("ST*835*0001~")
    assert is_edi_835(ERA_835)


# --- The upload parser refuses malformed bodies ---------------------------------------------------

BOUNDARY: Final = "b0undary"
CT: Final = f"multipart/form-data; boundary={BOUNDARY}"


def part(headers: str, data: bytes = PDF) -> bytes:
    return f"--{BOUNDARY}\r\n{headers}\r\n\r\n".encode() + data + f"\r\n--{BOUNDARY}--".encode()


GOOD_HEADERS: Final = 'Content-Disposition: form-data; name="file"; filename="eob.pdf"'


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (part(GOOD_HEADERS), "application/json"),
        (part(GOOD_HEADERS), "multipart/form-data"),
        (part(GOOD_HEADERS)[2:], CT),
        (part(GOOD_HEADERS).replace(b"--b0undary--", b"--b0undary"), CT),
        (part(GOOD_HEADERS) + b"\r\ntrailing", CT),
        (f"--{BOUNDARY}\r\n{GOOD_HEADERS}\r\n".encode() + PDF + f"\r\n--{BOUNDARY}--".encode(), CT),
        (
            part(GOOD_HEADERS).replace(
                f"\r\n--{BOUNDARY}--".encode(),
                f"\r\n--{BOUNDARY}\r\n{GOOD_HEADERS}\r\n\r\nx\r\n--{BOUNDARY}--".encode(),
            ),
            CT,
        ),
        (part('Content-Disposition: form-data; name="other"; filename="a.pdf"'), CT),
        (part('Content-Disposition: attachment; name="file"'), CT),
        (part("Content-Disposition"), CT),
        (part(GOOD_HEADERS).replace(b"eob.pdf", b"\xff\xfe.pdf"), CT),
    ],
    ids=[
        "json",
        "no-boundary",
        "bad-start",
        "no-closing",
        "trailing",
        "no-header-break",
        "two-parts",
        "wrong-name",
        "not-form-data",
        "header-without-colon",
        "non-utf8-header",
    ],
)
def test_us_5_1_multipart_parser_rejects_malformed_bodies(body: bytes, content_type: str) -> None:
    with pytest.raises(MalformedUploadError):
        parse_upload(body, content_type)


def test_us_5_1_multipart_parser_reads_names_and_types() -> None:
    quoted = f'multipart/form-data; boundary="{BOUNDARY}"; charset=utf-8'
    upload_file = parse_upload(part(GOOD_HEADERS) + b"\r\n", quoted)
    assert (upload_file.filename, upload_file.content_type, upload_file.data) == (
        "eob.pdf",
        "application/octet-stream",
        PDF,
    )
    windows = part('Content-Disposition: form-data; name="file"; filename="C:\\Users\\b\\x.pdf"')
    assert parse_upload(windows, CT).filename == "x.pdf"
    unix = part('Content-Disposition: form-data; name="file"; filename="/tmp/scan.png"')
    assert parse_upload(unix, CT).filename == "scan.png"
    nameless = part('Content-Disposition: form-data; name="file"')
    assert parse_upload(nameless, CT).filename is None
    blank = part('Content-Disposition: form-data; name="file"; filename=" "')
    assert parse_upload(blank, CT).filename is None
    with pytest.raises(UnsupportedDocumentError):
        parse_upload(part(GOOD_HEADERS, b""), CT)
    with pytest.raises(DocumentTooLargeError):
        parse_upload(part(GOOD_HEADERS, b"x" * (MAX_FILE_BYTES + 1)), CT)


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for chunk in parts:
        yield chunk


async def test_us_5_1_bodies_are_read_within_a_limit() -> None:
    assert await read_limited(chunks(b"ab", b"cd"), 4, None) == b"abcd"
    assert await read_limited(chunks(b"ab"), 4, "not-a-number") == b"ab"
    with pytest.raises(DocumentTooLargeError):
        await read_limited(chunks(b"ab", b"cde"), 4, None)
    with pytest.raises(DocumentTooLargeError):
        await read_limited(chunks(), 4, "5")  # refused before anything is read


# --- Refusals store nothing and echo nothing -----------------------------------------------------


async def test_us_5_1_refusals_store_nothing(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await new_case(desktop)
    secret = b"Jane Doe 1970-01-01"
    cases = f"{PREFIX}/cases"

    refused = [
        (await upload(desktop, case_id, *hermes_multipart(data=b"\x00\xff" + secret)), 415),
        (
            await desktop.post(
                f"{cases}/{case_id}/documents",
                content=b"x",
                headers={
                    "content-type": "multipart/form-data; boundary=x",
                    "content-length": str(MAX_FILE_BYTES * 2),
                },
            ),
            413,
        ),
        (
            await upload(desktop, case_id, b"--x\r\n" + secret, "multipart/form-data; boundary=x"),
            422,
        ),
        (await desktop.post(f"{cases}/{case_id}/documents", content=secret), 422),
        (await upload(desktop, "Jane Doe", *hermes_multipart()), 422),
        (await desktop.post(f"{cases}/{case_id}/paste", content=secret), 422),
        (await desktop.post(f"{cases}/{case_id}/paste", json={"text": ""}), 422),
        (await desktop.post(f"{cases}/{case_id}/paste", json={"text": "  "}), 415),
        (
            await desktop.post(
                f"{cases}/{case_id}/paste", json={"text": "x" * (MAX_PASTE_BYTES + 1)}
            ),
            413,
        ),
        (await desktop.post(f"{cases}/bad id/paste", json={"text": "x"}), 422),
        (await desktop.post(cases, content=b"{}"), 422),
        (await desktop.get(f"{cases}/case!"), 422),
    ]
    codes = {413: "document_too_large", 415: "unsupported_document", 422: "invalid_request"}
    for response, status in refused:
        assert_envelope(response, status, codes[status])
        assert secret not in response.content
    assert await documents(desktop, case_id) == []
    assert service.user_store("default").case_items(case_id, "source") == []


async def test_us_5_1_oversized_paste_body_refused_while_reading(
    desktop: httpx.AsyncClient,
) -> None:
    case_id = await new_case(desktop)
    body = b'{"text": "' + b"\\u0000" * (MAX_PASTE_BYTES + 1) + b'"}'
    response = await desktop.post(
        f"{PREFIX}/cases/{case_id}/paste",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert_envelope(response, 413, "document_too_large")


async def test_us_5_1_unknown_or_closed_case_refused(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    missing = "case_0000000000000000"
    assert_envelope(await desktop.get(f"{PREFIX}/cases/{missing}"), 404, "profile_not_found")
    case_id = await new_case(desktop)  # creates the profile's user scope
    assert_envelope(await desktop.get(f"{PREFIX}/cases/{missing}"), 404, "case_not_found")
    assert_envelope(await upload(desktop, missing, *hermes_multipart()), 404, "case_not_found")

    service.user_store("default").close_case(case_id)
    assert_envelope(await upload(desktop, case_id, *hermes_multipart()), 409, "case_closed")
    paste = await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": ERA_835})
    assert_envelope(paste, 409, "case_closed")
    case = Case.model_validate_json((await desktop.get(f"{PREFIX}/cases/{case_id}")).content)
    assert case.closed_at is not None
    assert case.documents == []


async def test_us_5_1_unknown_profile_has_no_cases(
    worker: tuple[WorkerClient, FastAPI], service: CorpusService
) -> None:
    transport = httpx.ASGITransport(app=worker[1])
    headers = {"Authorization": "Bearer corpus-test-token"}
    async with httpx.AsyncClient(transport=transport, base_url="http://w", headers=headers) as w:
        response = await w.get("/cases/case_0000000000000000", params={"profile": "nobody"})
        assert_envelope(response, 404, "profile_not_found")
        response = await w.post("/cases", params={"profile": "../escape"})
        assert_envelope(response, 422, "invalid_request")
    assert not (service.root / "profiles" / "nobody").exists()


# --- Attached files are purged with the case (BR-7) ----------------------------------------------


async def test_us_5_1_expired_attachments_purged(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    old, fresh = await new_case(desktop), await new_case(desktop)
    for case_id in (old, fresh):
        assert (await upload(desktop, case_id, *hermes_multipart())).status_code == 200
        await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": ERA_835})
    store = service.user_store("default")
    store.put_case_item(
        CaseItem(
            case_id=old,
            item_id="extraction",
            kind="extraction",
            created_at=utc_now(),
            payload=b"{}",
        ),
        audit=AuditAction.CASE_EXTRACTED,
    )
    now = utc_now()
    store.close_case(old, at=now - timedelta(days=91))
    store.close_case(fresh, at=now - timedelta(days=89))

    report = service.purge(PurgeRequest(profile="default"), now=now).reports[0]
    assert (report.cases, report.documents) == ([old], 2)
    assert store.case_items(old, "source") == []
    assert store.case_items(old, "extraction") == []
    assert len(store.case_items(fresh, "source")) == 2
    with sqlite3.connect(store.directory / DATABASE) as raw:
        assert raw.execute(
            "SELECT count(*) FROM case_items WHERE case_id = ?", (old,)
        ).fetchone() == (0,)
    # A purged case holds no content, so only the other closed case is still a candidate.
    assert store.expired_cases(now) == [fresh]


def test_us_5_1_case_items_of_unknown_case(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    with pytest.raises(CaseNotFoundError):
        store.case_items("nope", "source")
    store.create_case("c1")
    assert store.case_item_data("c1", "src_0000000000000000") is None
    item = CaseItem(
        case_id="c1", item_id="extraction", kind="extraction", created_at=utc_now(), payload=b"{}"
    )
    first = store.put_case_item(item, audit=AuditAction.CASE_EXTRACTED)
    later = item.model_copy(update={"created_at": utc_now() + timedelta(hours=1), "payload": b"[]"})
    again = store.put_case_item(later, audit=AuditAction.FIELD_CONFIRMED)
    assert again.created_at == first.created_at  # replacing keeps the first store time
    assert [i.payload for i in store.case_items("c1", "extraction")] == [b"[]"]
    assert store.case_item_data("c1", "extraction") is None


# --- The gateway only proxies (PC-4) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (413, "document_too_large"),
        (415, "unsupported_document"),
        (409, "case_closed"),
        (404, "case_not_found"),
        (404, "profile_not_found"),
    ],
)
async def test_us_5_1_gateway_relays_intake_codes(
    status: int, code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {"ok": False, "error": {"code": code, "message": "worker text"}}
        return httpx.Response(status, json=body)

    client = WorkerClient("http://worker", lambda: "t", transport=httpx.MockTransport(handler))
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    app.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        responses = [
            await desktop.post(f"{PREFIX}/cases", json={}),
            await desktop.get(f"{PREFIX}/cases/case_1"),
            await upload(desktop, "case_1", *hermes_multipart()),
            await desktop.post(f"{PREFIX}/cases/case_1/paste", json={"text": "x"}),
        ]
    for response in responses:
        assert_envelope(response, status, code)
    assert [(r.method, r.url.path, r.url.params["profile"]) for r in seen] == [
        ("POST", "/cases", "default"),
        ("GET", "/cases/case_1", "default"),
        ("POST", "/cases/case_1/documents", "default"),
        ("POST", "/cases/case_1/paste", "default"),
    ]
    body, content_type = hermes_multipart()
    assert seen[2].content == body  # forwarded unparsed
    assert seen[2].headers["content-type"] == content_type


async def test_us_5_1_gateway_reports_a_stopped_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    app.dependency_overrides[routes.get_worker_client] = lambda: WorkerClient(
        "http://worker", lambda: None
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        for response in (
            await desktop.post(f"{PREFIX}/cases", json={}),
            await desktop.get(f"{PREFIX}/cases/case_1"),
            await upload(desktop, "case_1", *hermes_multipart()),
            await desktop.post(f"{PREFIX}/cases/case_1/paste", json={"text": "x"}),
        ):
            assert_envelope(response, 503, "worker_unavailable")


# --- Review regressions ---------------------------------------------------------------------------


async def test_us_5_1_oversized_file_part_refused_by_the_worker(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    """A real 16 MiB + 1 byte part fits the body bound, so the worker's parser refuses it."""
    case_id = await new_case(desktop)
    body, content_type = hermes_multipart(data=PDF + b"0" * (MAX_FILE_BYTES + 1 - len(PDF)))
    assert_envelope(await upload(desktop, case_id, body, content_type), 413, "document_too_large")
    assert service.user_store("default").case_items(case_id, "source") == []


async def test_us_5_1_streamed_oversized_body_refused(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    """Without a Content-Length, the gateway stops reading at the bound."""
    case_id = await new_case(desktop)

    async def stream() -> AsyncIterator[bytes]:
        chunk = b"0" * (1024 * 1024)
        for _ in range(18):
            yield chunk

    response = await desktop.post(
        f"{PREFIX}/cases/{case_id}/documents",
        content=stream(),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )
    assert_envelope(response, 413, "document_too_large")
    assert service.user_store("default").case_items(case_id, "source") == []


async def test_us_5_1_closed_case_wins_over_the_file_check(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await new_case(desktop)
    service.user_store("default").close_case(case_id)
    unsupported = hermes_multipart(data=b"\x00\xff binary")
    assert_envelope(await upload(desktop, case_id, *unsupported), 409, "case_closed")
    blank = await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": "  "})
    assert_envelope(blank, 409, "case_closed")


def test_us_5_1_pdf_header_after_a_prefix() -> None:
    assert sniff(b"\r\n\x00scanner-prefix\n" + PDF) == "pdf"
    assert sniff(b"x" * 1024 + PDF) != "pdf"


async def test_us_5_1_small_bodies_are_bounded(desktop: httpx.AsyncClient) -> None:
    big = b'{"pad": "' + b"x" * (128 * 1024) + b'"}'
    response = await desktop.post(
        f"{PREFIX}/cases", content=big, headers={"content-type": "application/json"}
    )
    assert_envelope(response, 413, "document_too_large")
