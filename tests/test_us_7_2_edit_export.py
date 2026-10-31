"""US-7.2 Edit and Export the Draft (Python half).

Scenarios: edits are saved to the draft; export produces PDF; export produces DOCX. Also: edit and
export refusals, what an export holds (the stored draft, the label, Unicode text, every page), the
owner-only exports folder, the 15-minute expiry and its sweeper, and the gateway routes. The pane
scenarios run under ``node --test`` (``plugin/desktop/tests/appeal_draft.test.mjs``).
Rules: ES-1, ES-4, BR-2, BR-4, BR-6, BR-13, BR-14.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
import stat
import subprocess
import time
import zipfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx
import pymupdf
import pytest
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.cases.errors import DraftEditedError
from claimcoach.cases.extraction import JobStarted
from claimcoach.cases.models import Case
from claimcoach.cases.service import CaseService
from claimcoach.corpus.paths import InvalidProfileError, exports_dirs, profile_exports_dir
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction
from claimcoach.letters import draft as draft_module
from claimcoach.letters.export import (
    EXPORT_TTL,
    HEADER,
    Exports,
    render,
    render_docx,
    render_pdf,
)
from claimcoach.letters.types import AppealDraft, DraftEdit, ExportedFile, ExportFormat
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.jobs import JobRegistry
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.diagnosis import classification_reply, explanation_reply, role_models
from tests.fakes.drafting import LETTER, letter_reply
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_6_1_diagnosis import PREFIX, Sent, assert_envelope, open_case
from tests.test_us_7_1_appeal_draft import drafted_case

UNICODE = "Café naïve — “quoted” … 日本語 ✓\n\n  Indented line, kept.\r\nCRLF line."
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@pytest.fixture(scope="module")
def role_servers() -> Iterator[dict[ModelRole, FakeModelServer]]:
    """Fake Qwen3-8B, Qwen3-14B, and Bonsai 27B, each answering its own role's prompt."""
    replies = {
        ModelRole.CLASSIFICATION: classification_reply(),
        ModelRole.EXPLANATION: explanation_reply(),
        ModelRole.DRAFTING: letter_reply(),
    }
    servers = {role: FakeModelServer(replies={DEFAULT_MODEL_ID: r}) for role, r in replies.items()}
    for server in servers.values():
        server.start()
    yield servers
    for server in servers.values():
        server.stop()


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(service: CorpusService, role_servers: dict[ModelRole, FakeModelServer]) -> FastAPI:
    urls = {role: server.base_url for role, server in role_servers.items()}
    return create_app(TOKEN, corpus=service, pipeline_models=role_models(urls))


@pytest.fixture
async def desktop(
    worker: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway over ``worker``."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    sent: Sent = []
    gateway.dependency_overrides[routes.get_event_sink] = lambda: (
        lambda plugin, event, payload: sent.append((plugin, event, payload))
    )
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        desktop.worker = worker  # type: ignore[attr-defined]
        yield desktop


async def edit(desktop: httpx.AsyncClient, case_id: str, text: str) -> httpx.Response:
    return await desktop.post(f"{PREFIX}/cases/{case_id}/draft/text", json={"text": text})


async def export(desktop: httpx.AsyncClient, case_id: str, fmt: str) -> ExportedFile:
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/export", json={"format": fmt})
    assert response.status_code == 200, response.text
    return ExportedFile.model_validate_json(response.content)


def sample_draft(text: str = LETTER) -> AppealDraft:
    return AppealDraft(
        text=text,
        template_id="appeal",
        extraction_digest="0" * 64,
        diagnosed_at=datetime(2026, 10, 31, 12, tzinfo=UTC),
        drafted_at=datetime(2026, 10, 31, 12, 5, tzinfo=UTC),
    )


def pdf_text(data: bytes) -> list[str]:
    with pymupdf.open(stream=data, filetype="pdf") as pdf:  # type: ignore[no-untyped-call]
        assert pdf.is_pdf
        return [page.get_text(sort=True) for page in pdf]


def docx_paragraphs(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        assert package.testzip() is None
        root = ElementTree.fromstring(package.read("word/document.xml"))  # noqa: S314 - ours
    return ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p")]


# --- Scenario: Edits are saved to the draft ------------------------------------------------------


async def test_us_7_2_edits_saved(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    case_id = await drafted_case(desktop, service)
    before = (await open_case(desktop, case_id)).draft
    assert before is not None
    edited_text = LETTER.replace("To the appeals reviewer:", "Dear Appeals Reviewer,")

    response = await edit(desktop, case_id, f"  {edited_text}\n")

    assert response.status_code == 200, response.text
    answer = Case.model_validate_json(response.content)
    stored = (await open_case(desktop, case_id)).draft
    assert stored is not None
    assert stored.text == edited_text, "the stored draft contains the edited text"
    assert answer.draft == stored, "the answer shows what was stored"
    assert stored.edited_at is not None
    kept = stored.model_dump(exclude={"text", "edited_at"})
    assert kept == before.model_dump(exclude={"text", "edited_at"}), "label and provenance kept"
    actions = [entry.action for entry in service.user_store("default").audit_log(case_id)]
    assert AuditAction.DRAFT_EDITED in actions


async def test_us_7_2_edit_refusals(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    case = (await desktop.post(f"{PREFIX}/cases", json={})).json()
    assert_envelope(await edit(desktop, case["case_id"], "Text"), 409, "not_drafted")
    assert_envelope(await edit(desktop, "case_0000000000000000", "Text"), 404, "case_not_found")
    assert_envelope(await edit(desktop, "bad!id", "Text"), 422, "invalid_request")
    case_id = await drafted_case(desktop, service)
    for body in ({"text": "   "}, {"text": "x" * 20_001}, {"text": "x", "to": "payer"}, {}):
        response = await desktop.post(f"{PREFIX}/cases/{case_id}/draft/text", json=body)
        assert_envelope(response, 422, "invalid_request")
    not_json = await desktop.post(f"{PREFIX}/cases/{case_id}/draft/text", content=b"text")
    assert_envelope(not_json, 422, "invalid_request")
    service.user_store("default").close_case(case_id)
    assert_envelope(await edit(desktop, case_id, "Text"), 409, "case_closed")


async def test_us_7_2_edit_refused_while_drafting(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await drafted_case(desktop, service)
    worker: FastAPI = desktop.worker  # type: ignore[attr-defined]
    jobs: JobRegistry = worker.state.jobs
    gate = asyncio.Event()

    class Slow:
        async def run(self, _profile: str, _case_id: str, report: Any) -> None:
            await gate.wait()
            report("done", 1.0)

    jobs.start("default", case_id, "draft", runner=Slow())
    assert_envelope(await edit(desktop, case_id, "Mine."), 409, "model_busy")
    gate.set()
    await asyncio.sleep(0)
    for _ in range(50):
        if jobs.running("default", case_id) is None:
            break
        await asyncio.sleep(0.01)
    assert (await edit(desktop, case_id, "Mine.")).status_code == 200


async def test_us_7_2_a_worker_without_models_still_edits(service: CorpusService) -> None:
    """Editing needs no model: a worker without jobs saves the edit."""
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.save_draft("default", case_id, sample_draft())
    app = create_app(TOKEN, corpus=service)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app))
    case = await client.edit_draft("default", case_id, DraftEdit(text="Edited."))
    assert case.draft is not None
    assert case.draft.text == "Edited."


# --- Scenario: Export produces PDF ---------------------------------------------------------------


async def test_us_7_2_export_pdf(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    case_id = await drafted_case(desktop, service)

    exported = await export(desktop, case_id, "pdf")

    path = Path(exported.path)
    data = path.read_bytes()
    assert data.startswith(b"%PDF-")
    pages = pdf_text(data)
    text = " ".join(" ".join(pages).split())
    for line in LETTER.splitlines():
        assert " ".join(line.split()) in text, f"the PDF holds {line!r}"
    assert all(page.startswith(HEADER) for page in pages), "labeled on every page"
    assert (exported.format, exported.filename) == (ExportFormat.PDF, f"appeal-draft-{case_id}.pdf")
    assert exported.size_bytes == len(data)
    left = exported.expires_at - datetime.now(UTC)
    assert timedelta(minutes=14) < left <= timedelta(minutes=15)


def test_us_7_2_pdf_keeps_unicode_and_paginates() -> None:
    pages = pdf_text(render_pdf(sample_draft(UNICODE + "\n" + "A long paragraph. " * 900)))
    assert len(pages) > 1
    assert all(page.startswith(HEADER) for page in pages)
    first = pages[0]
    for fragment in ("Café naïve — “quoted” … 日本語 ✓", "Indented line, kept.", "CRLF line."):
        assert fragment in first
    with pymupdf.open(stream=render(sample_draft(), ExportFormat.PDF), filetype="pdf") as pdf:  # type: ignore[no-untyped-call]
        assert pdf.metadata["title"] == "Appeal letter (draft for human review)"


# --- Scenario: Export produces DOCX --------------------------------------------------------------


async def test_us_7_2_export_docx(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    case_id = await drafted_case(desktop, service)
    await edit(desktop, case_id, UNICODE)

    exported = await export(desktop, case_id, "docx")

    data = Path(exported.path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        names = package.namelist()
        types = ElementTree.fromstring(package.read("[Content_Types].xml"))  # noqa: S314 - ours
        rels = ElementTree.fromstring(package.read("_rels/.rels"))  # noqa: S314 - ours
        core = package.read("docProps/core.xml").decode()
    assert names[0] == "[Content_Types].xml"
    overrides = {o.get("PartName"): o.get("ContentType") for o in types if o.get("PartName")}
    assert str(overrides["/word/document.xml"]).endswith("wordprocessingml.document.main+xml")
    assert {r.get("Target") for r in rels} <= set(names), "every relationship resolves"
    assert "draft for human review" in core
    paragraphs = docx_paragraphs(data)
    assert paragraphs[0] == HEADER
    assert paragraphs[1:] == UNICODE.replace("\r\n", "\n").split("\n"), "a valid DOCX of the text"
    assert exported.filename == f"appeal-draft-{case_id}.docx"


@pytest.mark.skipif(shutil.which("textutil") is None, reason="macOS textutil reads DOCX")
def test_us_7_2_docx_reads_in_another_reader(tmp_path: Path) -> None:
    """An independent reader (macOS ``textutil``, Cocoa's Word importer) opens the file."""
    target = tmp_path / "draft.docx"
    target.write_bytes(render_docx(sample_draft(UNICODE)))
    text = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(target)],
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    ).stdout
    assert text.startswith(HEADER)
    assert "Café naïve — “quoted” … 日本語 ✓" in text
    assert "  Indented line, kept." in text
    assert "CRLF line." in text


def test_us_7_2_pdf_keeps_text_after_control_characters() -> None:
    """Review regression: a NUL ended MuPDF's text, so everything after it was missing."""
    text = "Dear reviewer,\nPatient seen on\x00 2026-01-02.\nPlease \x1breprocess.\nSincerely"
    (page,) = pdf_text(render_pdf(sample_draft(text)))
    for line in ("Patient seen on 2026-01-02.", "Please reprocess.", "Sincerely"):
        assert line in page
    assert "\x1b" not in page


def test_us_7_2_entity_text_is_kept_as_written() -> None:
    """Review regression: HTML entities in the letter were decoded a second time."""
    text = "AT&amp;T wrote x &lt; y; E&M and H&P codes; &#0; stays."
    (page,) = pdf_text(render_pdf(sample_draft(text)))
    assert text in " ".join(page.split())
    assert docx_paragraphs(render_docx(sample_draft(text)))[1] == text


def test_us_7_2_docx_drops_characters_xml_cannot_hold() -> None:
    draft = sample_draft("Bell\x07 and <tags> & \x00nulls\x1f.\ufffe")
    assert docx_paragraphs(render_docx(draft))[1] == "Bell and <tags> & nulls."
    edited = draft.model_copy(update={"edited_at": datetime(2026, 11, 1, tzinfo=UTC)})
    with zipfile.ZipFile(io.BytesIO(render_docx(edited))) as package:
        assert "2026-11-01T00:00:00Z" in package.read("docProps/core.xml").decode()


# --- Exports render the stored draft --------------------------------------------------------------


async def test_us_7_2_export_refusals(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    case = (await desktop.post(f"{PREFIX}/cases", json={})).json()
    url = f"{PREFIX}/cases/{case['case_id']}/export"
    assert_envelope(await desktop.post(url, json={"format": "pdf"}), 409, "not_drafted")
    missing = await desktop.post(
        f"{PREFIX}/cases/case_0000000000000000/export", json={"format": "pdf"}
    )
    assert_envelope(missing, 404, "case_not_found")
    case_id = await drafted_case(desktop, service)
    for body in ({"format": "rtf"}, {"format": "pdf", "text": "Injected"}, {}):
        response = await desktop.post(f"{PREFIX}/cases/{case_id}/export", json=body)
        assert_envelope(response, 422, "invalid_request")
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/bad!id/export", json={"format": "pdf"}),
        422,
        "invalid_request",
    )
    service.user_store("default").close_case(case_id)
    closed = await export(desktop, case_id, "docx")
    assert docx_paragraphs(Path(closed.path).read_bytes())[1:] == LETTER.split("\n"), (
        "a closed case still exports: reading changes nothing"
    )


# --- Scenario: Exports are short-lived and owner-only --------------------------------------------


async def test_us_7_2_export_is_audited(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    """Review: an export copies case content out of the encrypted store, so it is audited."""
    case_id = await drafted_case(desktop, service)
    await export(desktop, case_id, "pdf")
    entries = service.user_store("default").audit_log(case_id)
    assert AuditAction.DRAFT_EXPORTED in [entry.action for entry in entries]
    assert "pdf" not in repr(entries[-1].model_dump()), "IDs and times only"


async def test_us_7_2_edits_saved_while_drafting_are_kept(
    desktop: httpx.AsyncClient, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review regression: a draft job that ends after an edit no longer replaces it."""
    case_id = await drafted_case(desktop, service)
    cases: CaseService = desktop.worker.state.cases  # type: ignore[attr-defined]
    real = draft_module.draft_letter

    async def edited_meanwhile(*args: Any, **kwargs: Any) -> str:
        await asyncio.to_thread(cases.edit_draft, "default", case_id, DraftEdit(text="Mine."))
        return await real(*args, **kwargs)

    monkeypatch.setattr(draft_module, "draft_letter", edited_meanwhile)
    sent = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json={})
    started = JobStarted.model_validate_json(sent.content)
    worker: FastAPI = desktop.worker  # type: ignore[attr-defined]
    events = (await worker.state.jobs.events(started.job_id, 0, wait=0)).events
    while not events or events[-1].stage not in {"done", "failed"}:
        await asyncio.sleep(0.01)
        events = (await worker.state.jobs.events(started.job_id, 0, wait=0)).events
    assert (events[-1].stage, events[-1].error_code) == ("failed", "draft_edited")
    stored = (await open_case(desktop, case_id)).draft
    assert stored is not None
    assert stored.text == "Mine.", "the biller's edit is kept"
    with pytest.raises(DraftEditedError):
        cases.save_draft("default", case_id, sample_draft(), started=stored.drafted_at)
    cases.save_draft("default", case_id, sample_draft(), started=datetime.now(UTC))


async def test_us_7_2_export_files_are_owner_only(
    desktop: httpx.AsyncClient, service: CorpusService, tmp_path: Path
) -> None:
    case_id = await drafted_case(desktop, service)
    exported = await export(desktop, case_id, "pdf")
    path = Path(exported.path)
    assert path.parent == tmp_path / "hermes" / "plugin-data" / "claimcoach" / "exports"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert path.name.startswith(f"appeal-draft-{case_id}-")
    again = await export(desktop, case_id, "pdf")
    assert again.path != exported.path, "each export has its own random name"
    assert sorted(p.name for p in path.parent.iterdir()) == sorted(
        [path.name, Path(again.path).name]
    ), "no temporary file is left"


def test_us_7_2_a_failed_write_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exports = Exports(tmp_path)

    def fail(*_args: Any) -> None:
        raise OSError

    monkeypatch.setattr(os, "utime", fail)
    with pytest.raises(OSError):  # noqa: PT011 - the disk error itself
        exports.write("default", "case_0123456789abcdef", ExportFormat.PDF, b"%PDF-")
    assert list(profile_exports_dir("default", tmp_path).iterdir()) == []


def test_us_7_2_expired_export_removed(tmp_path: Path) -> None:
    now = [1_000_000.0]
    exports = Exports(tmp_path, clock=lambda: now[0])
    first = exports.write("default", "case_0123456789abcdef", ExportFormat.PDF, b"%PDF-")
    other = exports.write("billing-2", "case_fedcba9876543210", ExportFormat.DOCX, b"PK")
    folder = Path(first.path).parent
    unrelated = folder / "notes.txt"
    unrelated.write_text("not an export")
    os.utime(unrelated, (0, 0))
    stale_partial = folder / f".{Path(first.path).name}.partial"
    stale_partial.write_bytes(b"half")
    os.utime(stale_partial, (0, 0))

    now[0] += EXPORT_TTL - 1
    assert exports.sweep() == 1, "only the abandoned temporary file is old enough"
    assert Path(first.path).exists()
    assert Path(other.path).exists()

    now[0] += 2
    assert exports.sweep() == 2
    assert not Path(first.path).exists()
    assert not Path(other.path).exists()
    assert unrelated.exists(), "the sweep touches exports only"
    assert sorted(exports_dirs(tmp_path)) == sorted(
        [folder, tmp_path / "profiles" / "billing-2" / "plugin-data" / "claimcoach" / "exports"]
    )


def test_us_7_2_an_export_removed_meanwhile_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exports = Exports(tmp_path, clock=lambda: 0.0)
    written = Path(exports.write("default", "case_0123456789abcdef", ExportFormat.PDF, b"x").path)
    real_lstat = Path.lstat

    def gone(path: Path) -> os.stat_result:
        if path == written:
            raise FileNotFoundError
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", gone)
    assert Exports(tmp_path, clock=lambda: EXPORT_TTL * 2).sweep() == 0


def test_us_7_2_writing_sweeps_first(tmp_path: Path) -> None:
    now = [0.0]
    exports = Exports(tmp_path, clock=lambda: now[0])
    old = Path(exports.write("default", "case_0123456789abcdef", ExportFormat.PDF, b"x").path)
    now[0] = EXPORT_TTL + 1
    exports.write("default", "case_0123456789abcdef", ExportFormat.PDF, b"x")
    assert not old.exists()


def test_us_7_2_exports_folder_needs_a_profile_name(tmp_path: Path) -> None:
    with pytest.raises(InvalidProfileError):
        profile_exports_dir("../escape", tmp_path)
    assert exports_dirs(tmp_path) == []


async def test_us_7_2_sweeper_runs_on_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="claimcoach.letters")
    now = [0.0]
    exports = Exports(tmp_path, clock=lambda: now[0], interval=0.01)
    written = Path(exports.write("default", "case_0123456789abcdef", ExportFormat.PDF, b"x").path)
    now[0] = EXPORT_TTL + 1
    calls = [0]
    real_sweep = exports.sweep

    def sweep() -> int:
        calls[0] += 1
        if calls[0] == 2:
            raise PermissionError
        return real_sweep()

    monkeypatch.setattr(exports, "sweep", sweep)
    task = asyncio.create_task(exports.run())
    while calls[0] < 3:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not written.exists()
    assert "export sweep removed 1 expired exports" in caplog.text
    assert "export sweep failed: PermissionError" in caplog.text, "a bad run never ends it"


async def test_us_7_2_worker_lifespan_sweeps_and_clears(
    service: CorpusService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker sweeps on a schedule while it runs, and removes every export when it stops."""
    monkeypatch.setattr(Exports.__init__, "__kwdefaults__", {"clock": time.time, "interval": 0.01})
    folder = profile_exports_dir("default", tmp_path / "hermes")
    app = create_app(TOKEN, corpus=service)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)  # the first sweep has run
        old = folder / "appeal-draft-case_0123456789abcdef-0123456789abcdef.pdf"
        old.write_bytes(b"%PDF-")
        os.utime(old, (0, 0))
        for _ in range(100):
            if not old.exists():
                break
            await asyncio.sleep(0.01)
        assert not old.exists(), "a later sweep removes an export that expired meanwhile"
        fresh = folder / "appeal-draft-case_0123456789abcdef-fedcba9876543210.docx"
        fresh.write_bytes(b"PK")
        partial = folder / f".{fresh.name}.partial"
        partial.write_bytes(b"P")
        await asyncio.sleep(0.03)
        assert fresh.exists(), "an export is kept for its 15 minutes while the worker runs"
    assert not fresh.exists(), "every export goes when the worker stops (BR-6)"
    assert not partial.exists()


def test_us_7_2_clear_touches_exports_only(tmp_path: Path) -> None:
    exports = Exports(tmp_path)
    written = Path(exports.write("default", "case_0123456789abcdef", ExportFormat.PDF, b"x").path)
    other = written.parent / "notes.txt"
    other.write_text("kept")
    assert exports.clear() == 1
    assert not written.exists()
    assert other.exists()


# --- Through the gateway ------------------------------------------------------------------------


async def test_us_7_2_export_through_the_gateway(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    """``ctx.rest`` → ``plugin_api.py`` → worker: the pane gets the path for the save dialog."""
    case_id = await drafted_case(desktop, service)
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/export", json={"format": "docx"})
    body = response.json()
    assert set(body) == {
        "ok",
        "case_id",
        "format",
        "path",
        "filename",
        "size_bytes",
        "expires_at",
    }
    assert Path(body["path"]).is_file()
    assert "ACME" not in body["path"], "the path holds IDs only"
