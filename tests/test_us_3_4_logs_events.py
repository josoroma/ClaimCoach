"""US-3.4: PHI-free logs and events.

Rules: ES-8, BR-14, PC-4. The log scenario runs a live worker (uvicorn on loopback, the JSON
handler from ``configure_logging``, a fake PHI model-server *process* started by the model
manager) and captures every line the process writes while a case's documents are redacted.
"""

from __future__ import annotations

import io
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from claimcoach.agent.guard import redact_tool_result
from claimcoach.api.client import WorkerClient
from claimcoach.events import (
    CASE_ID_PATTERN,
    JOB_ID_PATTERN,
    CaseProgressEvent,
    CaseStage,
    hermes_sink,
    new_case_id,
    new_job_id,
    publish,
)
from claimcoach.logs import (
    JsonFormatter,
    configure_logging,
    get_logger,
    job_context,
    request_id_var,
    scrub,
)
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.redact.ledger import LEDGER, PhiLedger
from claimcoach.redact.types import PhiCategory, PhiSpan, RedactRequest
from claimcoach.worker.app import create_app, get_health
from tests.conftest import REPO_ROOT, free_port_in_range
from tests.fakes.live_app import LiveApp
from tests.fakes.model_env import build_model_env, fake_server_command
from tests.fakes.phi import PHI_DOCUMENTS, fake_phi_reply, leaked_strings, seeded_strings
from tests.fixtures.phi.generate import PhiDocument

TOKEN = "l" * 43
CASE = PHI_DOCUMENTS[:3]  # one case: an EOB, a denial letter, a call note


@pytest.fixture(autouse=True)
def _clean_ledger() -> Iterator[None]:
    LEDGER.clear()
    yield
    LEDGER.clear()


def document_lines(*documents: PhiDocument) -> list[str]:
    """Lines of document text long enough to be recognizable."""
    return [
        line.strip()
        for document in documents
        for line in document["text"].splitlines()
        if len(line.strip()) >= 20
    ]


def phi_in(text: str, *documents: PhiDocument) -> list[str]:
    return leaked_strings(text, *documents)


# --- Scenario: Logs are structured JSON without document text ---


def test_us_3_4_logs_json_without_document_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))  # model servers run the fake from the repo
    stream = io.StringIO()
    configure_logging("worker", stream)
    reply_file = tmp_path / "phi-reply.json"
    reply_file.write_text(fake_phi_reply(*CASE))
    shared = {
        "command": fake_server_command("--model", DEFAULT_MODEL_ID, "--reply-file", str(reply_file))
    }
    env = build_model_env(tmp_path, roles={"phi_detection": shared, "classification": shared})
    app = create_app(TOKEN, env.manager())
    text = "\n\n".join(d["text"] for d in CASE)

    def fail_with_document() -> Any:
        raise RuntimeError(f"could not parse {text}")

    with LiveApp(app) as worker:
        url, auth = worker.base_url, {"Authorization": f"Bearer {TOKEN}"}
        with httpx.Client(base_url=url, headers=auth, trust_env=False, timeout=60) as client:
            redacted = client.post("/redact", json={"text": text})
            assert redacted.status_code == 200
            assert (
                client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
            )
            app.dependency_overrides[get_health] = fail_with_document
            assert client.get("/health").status_code == 500
            app.dependency_overrides.clear()

        async def scrub_via_worker(value: str) -> str:
            worker_client = WorkerClient(url, lambda: TOKEN, timeout=60)
            return (await worker_client.redact(RedactRequest(text=value))).text

        guarded = redact_tool_result(
            lambda _a, **_k: json.dumps({"summary": text}), scrubber=scrub_via_worker
        )
        assert phi_in(guarded({}), *CASE) == []
        # A careless log call in pipeline code, inside a case job, quoting the patient.
        with job_context("case-0001"):
            get_logger("claimcoach.pipeline").warning(
                "case for %s (%s) stalled", CASE[0]["phi"]["name"][0], CASE[0]["phi"]["ssn"][0]
            )
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]  # every line is valid JSON

    assert len(records) >= 5
    for record in records:
        assert set(record) >= {"ts", "level", "logger", "message", "request_id", "job_id"}
        assert record["request_id"] or record["job_id"], record
    log_text = "\n".join(lines)
    assert phi_in(log_text, *CASE) == []
    for line in document_lines(*CASE):
        assert line not in log_text
    messages = [r["message"] for r in records]
    assert any(m.startswith("model server on port") for m in messages), "manager logs captured"
    assert any(m.startswith("rejected GET /health") for m in messages)
    assert any(m == "unhandled RuntimeError on GET /health" for m in messages)
    assert "case for [NAME] ([SSN]) stalled" in messages
    stalled = next(r for r in records if r["message"].startswith("case for"))
    assert stalled["job_id"] == "case-0001"
    assert redacted.headers["X-Request-ID"] in {r["request_id"] for r in records}


def test_us_3_4_exception_text_is_never_logged() -> None:
    stream = io.StringIO()
    configure_logging("worker", stream)

    def parse() -> None:
        raise ValueError(PHI_DOCUMENTS[0]["text"])

    try:
        parse()
    except ValueError:
        get_logger("claimcoach.test").exception("step failed")
        logging.getLogger("thirdparty.lib").exception("foreign logger failed")
    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["exc_type"] == second["exc_type"] == "ValueError"
    assert phi_in(stream.getvalue(), PHI_DOCUMENTS[0]) == []
    assert "Traceback" not in stream.getvalue()


def test_us_3_4_foreign_loggers_are_scrubbed_by_the_formatter() -> None:
    record = logging.LogRecord(
        "uvicorn.error", logging.INFO, __file__, 1, "ssn %s", ("123-45-6789",), None
    )
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "ssn [SSN]"
    assert line["job_id"] == f"process-{os.getpid()}"
    assert "exc_type" not in line


def test_us_3_4_request_and_job_ids() -> None:
    record = logging.LogRecord("claimcoach.x", logging.INFO, __file__, 1, "m", None, None)
    token = request_id_var.set("abc123")
    try:
        assert json.loads(JsonFormatter().format(record))["request_id"] == "abc123"
        assert json.loads(JsonFormatter().format(record))["job_id"] is None
        with job_context("download-drafting"):
            assert json.loads(JsonFormatter().format(record))["job_id"] == "download-drafting"
    finally:
        request_id_var.reset(token)
    assert json.loads(JsonFormatter().format(record))["request_id"] is None


def test_us_3_4_ledger_is_bounded_and_skips_short_values() -> None:
    ledger = PhiLedger(size=2)
    text = "Jo Avery Ilyasova Glenhaven"
    spans = [
        PhiSpan(start=0, end=2, category=PhiCategory.NAME, source="model"),
        PhiSpan(start=3, end=8, category=PhiCategory.NAME, source="model"),
        PhiSpan(start=9, end=17, category=PhiCategory.NAME, source="model"),
        PhiSpan(start=18, end=27, category=PhiCategory.ADDRESS, source="model"),
    ]
    ledger.remember(text, spans)
    assert scrub("avery, ilyasova and glenhaven; jo", ledger) == "avery, [NAME] and [ADDRESS]; jo"
    ledger.clear()
    assert scrub("ilyasova", ledger) == "ilyasova"


def test_us_3_4_ledger_remembers_each_part_of_a_name() -> None:
    ledger = PhiLedger()
    text = "Avery Vandermeer"
    ledger.remember(text, [PhiSpan(start=0, end=16, category=PhiCategory.NAME, source="model")])
    assert scrub("retry for Vandermeer", ledger) == "retry for [NAME]"
    assert scrub("VANDERMEER, AVERY", ledger) == "[NAME], [NAME]"


def test_us_3_4_unformattable_log_calls_never_leak_or_raise() -> None:
    stream = io.StringIO()
    configure_logging("worker", stream)
    name, ssn = PHI_DOCUMENTS[0]["phi"]["name"][0], PHI_DOCUMENTS[0]["phi"]["ssn"][0]
    get_logger("claimcoach.x").info("case %d", f"{name} {ssn}")  # must not raise into the caller
    logging.getLogger("thirdparty").info("parsed %d fields", f"{name} SSN {ssn}")
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [line["message"] for line in lines] == [
        "[unformattable log call] case %d",
        "[unformattable log call] parsed %d fields",
    ]
    assert phi_in(stream.getvalue(), PHI_DOCUMENTS[0]) == []


def test_us_3_4_handler_errors_are_one_json_line() -> None:
    class Broken:
        def __str__(self) -> str:
            raise RuntimeError(PHI_DOCUMENTS[0]["text"])

    stream = io.StringIO()
    handler = configure_logging("worker", stream)
    handler.setFormatter(logging.Formatter("%(message)s"))  # a formatter that can fail
    logging.getLogger("thirdparty").info(Broken())
    (line,) = (json.loads(raw) for raw in stream.getvalue().splitlines())
    assert line["message"] == "logging failed"
    assert line["exc_type"] == "RuntimeError"
    assert phi_in(stream.getvalue(), PHI_DOCUMENTS[0]) == []


def test_us_3_4_uncaught_exceptions_are_json_type_only() -> None:
    stream = io.StringIO()
    configure_logging("worker", stream)
    error = OSError(PHI_DOCUMENTS[0]["text"])
    sys.excepthook(OSError, error, None)

    def crash() -> None:
        raise ValueError(PHI_DOCUMENTS[0]["text"])

    thread = threading.Thread(target=crash, name="pipeline")
    thread.start()
    thread.join()
    messages = [json.loads(line)["message"] for line in stream.getvalue().splitlines()]
    assert messages == ["uncaught OSError", "uncaught ValueError in thread pipeline"]
    assert phi_in(stream.getvalue(), PHI_DOCUMENTS[0]) == []


def test_us_3_4_real_worker_process_logs_only_json(tmp_path: Path) -> None:
    """``python -m claimcoach.worker`` as the launcher runs it: every stderr line is JSON."""
    env_dir = tmp_path / "models-env"
    env_dir.mkdir()
    reply_file = tmp_path / "phi-reply.json"
    reply_file.write_text(fake_phi_reply(*CASE))
    command = fake_server_command("--model", DEFAULT_MODEL_ID, "--reply-file", str(reply_file))
    shared = {"command": command}
    models = build_model_env(env_dir, roles={"phi_detection": shared, "classification": shared})
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "models.yaml").write_text((env_dir / "models.yaml").read_text())
    port = free_port_in_range(18215)
    log_path = tmp_path / "worker.log"
    env = {**os.environ, "MODELS_HOME": str(models.home), "PYTHONPATH": str(REPO_ROOT)}
    text = "\n\n".join(d["text"] for d in CASE)
    with log_path.open("w") as log:
        worker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "claimcoach.worker",
                "--data-dir",
                str(data_dir),
                "--port",
                str(port),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=REPO_ROOT / "plugin",
        )
        try:
            token_path = data_dir / "worker" / "token"
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base, trust_env=False, timeout=60) as client:
                wait_until_serving(client, token_path, worker)
                auth = {"Authorization": f"Bearer {token_path.read_text()}"}
                assert client.post("/redact", json={"text": text}, headers=auth).status_code == 200
                bad = client.get("/health", headers={"Authorization": "Bearer nope"})
                assert bad.status_code == 401
                too_long = client.post("/redact", json={"text": "x" * 300_000}, headers=auth)
                assert too_long.status_code == 422
        finally:
            worker.send_signal(signal.SIGTERM)
            worker.wait(timeout=30)
    lines = [line for line in log_path.read_text().splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]  # every line, startup to shutdown, is JSON
    assert records
    assert phi_in(log_path.read_text(), *CASE) == []
    rejected = [r for r in records if r["message"].startswith("rejected GET /health")]
    assert rejected
    assert all(r["request_id"] for r in rejected), "lines written during a request carry its ID"
    assert bad.headers["X-Request-ID"] in {r["request_id"] for r in rejected}
    assert any(r["message"].startswith("model server on port") for r in records)


def wait_until_serving(
    client: httpx.Client, token_path: Path, worker: subprocess.Popen[bytes]
) -> None:
    for _ in range(300):
        assert worker.poll() is None, "the worker exited"
        if token_path.exists():
            try:
                client.get("/health")
            except httpx.TransportError:
                pass
            else:
                return
        threading.Event().wait(0.05)
    pytest.fail("the worker did not start")


# --- Scenario: Broadcast events carry no PHI ---


def test_us_3_4_events_carry_no_phi() -> None:
    sent: list[tuple[str, str, dict[str, Any]]] = []
    stages: list[CaseStage] = [
        "uploaded",
        "extracting",
        "redacting",
        "classifying",
        "explaining",
        "drafting",
        "done",
    ]
    case_id, job_id = new_case_id(), new_job_id()  # how the pipeline names a case and its job
    for index, stage in enumerate(stages):
        event = CaseProgressEvent(case_id=case_id, job_id=job_id, stage=stage, progress=index / 6)
        assert publish(event, sink=lambda *call: sent.append(call))
    failed = CaseProgressEvent(
        case_id=case_id, job_id=job_id, stage="failed", progress=1, error_code="model_busy"
    )
    publish(failed, sink=lambda *call: sent.append(call))

    assert {(plugin, name) for plugin, name, _ in sent} == {("claimcoach", "case.progress")}
    wire = json.dumps([payload for _, _, payload in sent])
    assert phi_in(wire, *CASE) == []
    for line in document_lines(*CASE):
        assert line not in wire


PHI_SHAPED = sorted(
    {value for document in PHI_DOCUMENTS for value in seeded_strings(document)}
    | {"1985-03-12", "123-45-6789", "4829173", "ABC123456789", "Vandermeer", "Jane_Doe", "case_1"}
)
"""Every seeded value of every fixture (all DOB formats, SSNs, MRNs, member IDs, single-word
surnames) plus the PHI-shaped IDs the review found accepted by the first ID pattern."""


@pytest.mark.parametrize("value", PHI_SHAPED)
@pytest.mark.parametrize("field", ["case_id", "job_id"])
def test_us_3_4_event_ids_reject_phi_shaped_values(field: str, value: str) -> None:
    fields: dict[str, Any] = {
        "case_id": new_case_id(),
        "job_id": new_job_id(),
        "stage": "done",
        "progress": 1.0,
    }
    with pytest.raises(ValidationError):
        CaseProgressEvent(**(fields | {field: value}))


@pytest.mark.parametrize(
    "override",
    [
        {"job_id": PHI_DOCUMENTS[0]["text"]},
        {"stage": "patient Avery called"},
        {"patient": "Avery"},
        {"error_code": "Avery"},
    ],
)
def test_us_3_4_event_payloads_reject_free_text(override: dict[str, Any]) -> None:
    fields: dict[str, Any] = {
        "case_id": new_case_id(),
        "job_id": new_job_id(),
        "stage": "done",
        "progress": 1.0,
    }
    with pytest.raises(ValidationError):
        CaseProgressEvent(**(fields | override))


def test_us_3_4_event_fields_cannot_carry_text() -> None:
    """Every string in the event schema is an enum, a constant, or an ID pattern."""

    def strings(node: Any) -> Iterator[dict[str, Any]]:
        if isinstance(node, dict):
            if node.get("type") == "string":
                yield node
            for value in node.values():
                yield from strings(value)
        elif isinstance(node, list):
            for item in node:
                yield from strings(item)

    found = list(strings(CaseProgressEvent.model_json_schema()))
    assert found
    for schema in found:
        assert (
            "enum" in schema
            or "const" in schema
            or schema.get("pattern") in {CASE_ID_PATTERN, JOB_ID_PATTERN}
        ), schema


def test_us_3_4_publish_uses_hermes_broadcast_inside_the_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = CaseProgressEvent(case_id=new_case_id(), job_id=new_job_id(), stage="done", progress=1)
    assert hermes_sink() is None
    assert publish(event) is False  # no gateway in this process: logged, not sent

    sent: list[tuple[Any, ...]] = []
    fake = types.ModuleType("hermes_cli.plugin_events")
    fake.broadcast_plugin_event = lambda *call: sent.append(call)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugin_events", fake)
    assert publish(event) is True
    assert sent == [("claimcoach", "case.progress", event.model_dump(mode="json"))]
