"""US-3.2: Handler-level redaction of agent tool results.

Rules: BR-3, PC-7, PC-8, BR-14. The redactor is the real worker ``/redact`` route on a loopback
socket, backed by the fake PHI model; the guard reaches it from its own thread and event loop as
it does inside the Hermes gateway.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from claimcoach.agent import guard
from claimcoach.agent.guard import (
    HOOK_NAME,
    HOOK_TIMEOUT,
    Scrubber,
    guard_text,
    make_hook,
    redact_tool_result,
    register_guard_hook,
)
from claimcoach.agent.tools import TOOLS, ToolSpec, register_agent, register_tools
from claimcoach.api.client import WorkerClient, WorkerUnavailableError
from claimcoach.api.models import ERROR_MESSAGES, envelope
from claimcoach.redact.detector import PhiDetector
from claimcoach.redact.redactor import Redactor
from claimcoach.redact.types import MAX_TEXT_CHARS, RedactRequest
from claimcoach.worker.app import create_app
from claimcoach.worker.config import WorkerConfig
from tests.conftest import HERMES_ROOT, PLUGIN_DIR, REPO_ROOT, free_port_in_range
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.live_app import LiveApp
from tests.fakes.phi import (
    PHI_DOCUMENTS,
    fake_phi_reply,
    leaked_strings,
    serve_phi,
    static_models,
)
from tests.fakes.registrar import FakeRegistrar
from tests.fixtures.phi.generate import PhiDocument

TOKEN = "g" * 43
CASE = PHI_DOCUMENTS[1]
ARGS: dict[str, dict[str, str]] = {
    "claimcoach_explain_code": {"code": "CO-197"},
    "claimcoach_payer_rules": {"payer": "Harborline Health Plan"},
    "claimcoach_case_summary": {"case_id": "case_01"},
}
FAILED = envelope("redaction_failed").model_dump_json()


@pytest.fixture(scope="module")
def worker() -> Iterator[LiveApp]:
    with FakeModelServer() as phi_model:
        serve_phi(phi_model, fake_phi_reply(*PHI_DOCUMENTS))
        redactor = Redactor(PhiDetector(static_models(phi_model.base_url)))
        with LiveApp(create_app(TOKEN, redactor=redactor)) as live:
            yield live


def scrubber_for(worker: LiveApp) -> Scrubber:
    async def scrub(text: str) -> str:
        client = WorkerClient(worker.base_url, lambda: TOKEN, timeout=10)
        return (await client.redact(RedactRequest(text=text))).text

    return scrub


def case_result(document: PhiDocument = CASE) -> str:
    """What a careless handler might return about a case: its document text."""
    return json.dumps({"ok": True, "case_id": "case_01", "summary": document["text"]})


def leaked(text: str, document: PhiDocument = CASE) -> list[str]:
    return leaked_strings(text, document)


@pytest.fixture
def leaking_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every tool handler return the seeded case, as a bug in a later story might."""

    def leak(_self: ToolSpec, _args: Mapping[str, Any], **_context: Any) -> str:
        return case_result()

    monkeypatch.setattr(ToolSpec, "handle", leak)


def hermes_dispatch(registrar: FakeRegistrar, name: str, args: Mapping[str, Any]) -> str:
    """Hermes v0.22.5 tool dispatch + ``transform_tool_result`` (``model_tools.py``):

    the handler result is passed to every hook callback; each callback is isolated and a raising
    one is skipped (``plugins_dispatch.invoke_hook``); the first ``str`` wins; with no string the
    original result is kept (fail-open, PC-7).
    """
    result = registrar.tools[name]["handler"](args, task_id="t1")
    replies = []
    for callback in registrar.hooks.get(HOOK_NAME, []):
        try:
            reply = callback(tool_name=name, args=args, result=result, task_id="t1")
        except Exception:  # noqa: BLE001, S112 - mirrors Hermes' per-callback isolation
            continue
        if reply is not None:
            replies.append(reply)
    return next((r for r in replies if isinstance(r, str)), result)


# --- Scenario: Tool results are PHI-free without the hook ---


@pytest.mark.usefixtures("leaking_handlers")
def test_us_3_2_tool_results_phi_free_without_hook(worker: LiveApp) -> None:
    registrar = FakeRegistrar()
    names = register_tools(registrar, scrubber_for(worker))
    assert registrar.hooks == {}, "no transform_tool_result hook in this scenario"
    assert names == [tool.name for tool in TOOLS]
    for name in names:
        raw = registrar.tools[name]["handler"](ARGS[name], task_id="t1")
        assert isinstance(raw, str), "PC-8"
        body = json.loads(raw)
        assert body["case_id"] == "case_01"
        assert leaked(raw) == [], name
        assert "[NAME]" in body["summary"]
        assert "CO-197" in body["summary"], "codes stay useful to the agent"


def test_us_3_2_every_registered_handler_is_guarded() -> None:
    registrar = FakeRegistrar()
    register_agent(registrar)
    for name, call in registrar.tools.items():
        assert getattr(call["handler"], "__claimcoach_guarded__", False), name
    assert len(registrar.hooks[HOOK_NAME]) == 1


# --- Scenario: The hook re-redacts as a second guard ---


def test_us_3_2_hook_re_redacts(worker: LiveApp) -> None:
    registrar = FakeRegistrar()
    register_guard_hook(registrar, scrubber_for(worker))
    (hook,) = registrar.hooks[HOOK_NAME]
    for document in PHI_DOCUMENTS[:3]:
        out = hook(
            tool_name="claimcoach_case_summary",
            args={"case_id": "case_01"},
            result=case_result(document),
            task_id="t1",
            session_id="s1",
            tool_call_id="c1",
            duration_ms=3,
        )
        assert isinstance(out, str)
        assert leaked(out, document) == []
        assert json.loads(out)["case_id"] == "case_01"


def test_us_3_2_hook_leaves_other_tools_alone() -> None:
    def never(_text: str) -> Any:
        raise AssertionError("other tools are not redacted by ClaimCoach")

    hook = make_hook(never)
    assert hook(tool_name="read_file", args={}, result="Jane Doe", task_id="t") is None
    assert hook(tool_name="claimcoach_case_summary", args={}, result={"x": 1}) is None


# --- Scenario: A failing hook does not expose PHI ---


def raising_hook(**_payload: Any) -> str:
    raise RuntimeError("hook bug: Avery Vandermeer")


@pytest.mark.usefixtures("leaking_handlers")
def test_us_3_2_failing_hook_does_not_expose_phi(worker: LiveApp) -> None:
    registrar = FakeRegistrar()
    register_tools(registrar, scrubber_for(worker))
    registrar.hooks[HOOK_NAME] = [raising_hook]  # the transform_tool_result hook raises

    received = hermes_dispatch(
        registrar, "claimcoach_case_summary", ARGS["claimcoach_case_summary"]
    )
    assert leaked(received) == []
    assert "[NAME]" in json.loads(received)["summary"], "the handler-redacted result reached it"


@pytest.mark.usefixtures("leaking_handlers")
def test_us_3_2_hook_whose_redaction_fails_keeps_the_handler_result(worker: LiveApp) -> None:
    """ClaimCoach's own hook never raises: on failure it leaves the handler's result alone."""

    async def broken(_text: str) -> str:
        raise RuntimeError("hook bug: Avery Vandermeer")

    registrar = FakeRegistrar()
    register_tools(registrar, scrubber_for(worker))
    register_guard_hook(registrar, broken)
    (hook,) = registrar.hooks[HOOK_NAME]
    assert hook(tool_name="claimcoach_case_summary", result=case_result()) is None
    received = hermes_dispatch(
        registrar, "claimcoach_case_summary", ARGS["claimcoach_case_summary"]
    )
    assert leaked(received) == []
    assert "[NAME]" in json.loads(received)["summary"]
    assert make_hook().__name__ == "transform_tool_result"
    assert HOOK_TIMEOUT < 30, "under Hermes' plugins.hook_callback_timeout"


# --- Fail closed ---


@pytest.mark.parametrize("token", [None, TOKEN], ids=["no-token", "stale-token-port-closed"])
def test_us_3_2_unreachable_worker_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str | None
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    if token is not None:  # a token left by a worker that is no longer listening
        port = free_port_in_range(18210)
        monkeypatch.setattr(
            guard, "WorkerConfig", lambda data_dir: WorkerConfig(data_dir=data_dir, port=port)
        )
        token_path = WorkerConfig(data_dir=tmp_path / "hermes/plugin-data/claimcoach").token_path
        token_path.parent.mkdir(parents=True)
        token_path.write_text(token)
    handler = redact_tool_result(lambda _args, **_kw: case_result())
    assert handler({}) == FAILED
    assert json.loads(FAILED)["error"]["message"] == ERROR_MESSAGES["redaction_failed"]


def test_us_3_2_default_scrubber_reaches_the_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``worker_scrubber`` resolves the data dir and token like the gateway does."""
    port = free_port_in_range(18210)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setattr(
        guard, "WorkerConfig", lambda data_dir: WorkerConfig(data_dir=data_dir, port=port)
    )
    token_path = WorkerConfig(data_dir=tmp_path / "hermes/plugin-data/claimcoach").token_path
    token_path.parent.mkdir(parents=True)
    token_path.write_text(TOKEN)
    with FakeModelServer() as phi_model:
        serve_phi(phi_model, fake_phi_reply(CASE))
        app = create_app(TOKEN, redactor=Redactor(PhiDetector(static_models(phi_model.base_url))))
        with LiveApp(app, port=port):
            out = redact_tool_result(lambda _args, **_kw: case_result())({})
            # The path plugin/__init__.py takes: register_agent with the default scrubber.
            registrar = FakeRegistrar()
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(ToolSpec, "handle", lambda *_a, **_k: case_result())
                register_agent(registrar)
            registered = [
                call["handler"](ARGS[name], task_id="t1") for name, call in registrar.tools.items()
            ]
            hooked = registrar.hooks[HOOK_NAME][0](
                tool_name="claimcoach_case_summary", result=case_result()
            )
    for text in (out, *registered, hooked):
        assert leaked(text) == []
        assert "[NAME]" in text


def test_us_3_2_handler_exception_text_never_reaches_the_agent() -> None:
    def explode(_args: Mapping[str, Any], **_kw: Any) -> str:
        raise ValueError(f"cannot parse {CASE['text']}")

    raw = redact_tool_result(explode, scrubber=scrubber_never())({})
    assert raw == envelope("internal_error").model_dump_json()


def scrubber_never() -> Scrubber:
    async def scrub(_text: str) -> str:
        raise AssertionError("not called")

    return scrub


def test_us_3_2_fixed_envelopes_skip_the_model() -> None:
    for code in ("not_implemented", "invalid_request"):
        raw = envelope(code).model_dump_json()
        assert guard_text(raw, scrubber_never()) == raw
    # An envelope-shaped result whose message is not the fixed one is redacted like any other.
    forged = json.dumps({"ok": False, "error": {"code": "not_found", "message": "Jane Doe"}})
    assert guard_text(forged, scrubber_never_ok(), fallback=FAILED) == FAILED
    assert guard_text(forged, scrubber_never_ok()) is None


def scrubber_never_ok() -> Scrubber:
    async def scrub(_text: str) -> str:
        raise WorkerUnavailableError

    return scrub


def test_us_3_2_slow_redaction_times_out_closed() -> None:
    async def slow(text: str) -> str:
        await asyncio.sleep(5)
        return text

    started = time.monotonic()
    assert guard_text(case_result(), slow, timeout=0.2, fallback=FAILED) == FAILED
    assert time.monotonic() - started < 2


def test_us_3_2_a_blocked_redaction_thread_is_abandoned() -> None:
    async def stuck(text: str) -> str:
        time.sleep(1.6)  # blocks the loop: wait_for cannot interrupt it
        return text

    started = time.monotonic()
    assert guard_text(case_result(), stuck, timeout=0.2, fallback=FAILED) == FAILED
    assert time.monotonic() - started < 1.5


def test_us_3_2_json_results_are_redacted_field_by_field() -> None:
    seen: list[str] = []

    async def names(text: str) -> str:
        seen.append(text)
        return text.replace("Jane Doe", "[NAME]")

    result = json.dumps({"case": "c1", "Jane Doe": ["Dear Jane Doe,\nthanks", 3, None, True]})
    redacted = guard_text(result, names)
    assert redacted is not None
    assert json.loads(redacted) == {
        "case": "c1",
        "[NAME]": ["Dear [NAME],\nthanks", 3, None, True],
    }
    assert "\\n" not in seen[0], "the redactor sees decoded text, not JSON escapes"
    assert guard_text("Jane Doe called", names) == "[NAME] called"
    assert guard_text("[null, true, {}]", scrubber_never()) == "[null, true, {}]"


def test_us_3_2_numeric_identifiers_are_redacted(worker: LiveApp) -> None:
    result = json.dumps({"mrn": 4454893, "ssn": 322639968, "pages": 3, "ratio": 0.5})
    redacted = guard_text(result, scrubber_for(worker))
    assert redacted is not None
    body = json.loads(redacted)
    assert body == {"mrn": "[MRN]", "ssn": "[SSN]", "pages": 3, "ratio": 0.5}


def test_us_3_2_oversize_result_fails_closed_without_quoting_it() -> None:
    oversize = json.dumps({"summary": CASE["text"] * (MAX_TEXT_CHARS // len(CASE["text"]) + 1)})
    raw = redact_tool_result(lambda _a, **_k: oversize, scrubber=scrubber_never())({})
    assert raw == FAILED
    assert leaked(raw) == []


def test_us_3_2_keys_that_redact_alike_fail_closed() -> None:
    async def names(text: str) -> str:
        return text.replace("Jane Doe", "[NAME]").replace("John Roe", "[NAME]")

    result = json.dumps({"Jane Doe": 1, "John Roe": 2})
    assert guard_text(result, names, fallback=FAILED) == FAILED


def test_us_3_2_non_string_results_are_handler_bugs() -> None:
    raw = redact_tool_result(lambda _a, **_k: {"summary": CASE["text"]}, scrubber=scrubber_never())
    assert raw({}) == envelope("internal_error").model_dump_json()


def test_us_3_2_redaction_that_loses_a_field_is_withheld() -> None:
    async def merge(text: str) -> str:
        return text.replace("\x1e", "")

    assert guard_text(case_result(), merge, fallback=FAILED) == FAILED


async def test_us_3_2_guard_works_inside_a_running_loop(worker: LiveApp) -> None:
    """Hermes may call sync handlers from a thread whose event loop is running."""
    handler = redact_tool_result(lambda _a, **_k: case_result(), scrubber=scrubber_for(worker))
    assert leaked(handler({})) == []


# --- The same scenarios through the real Hermes dispatch (Hermes Agent v0.22.5) ---


@pytest.mark.hermes
def test_us_3_2_real_hermes_dispatch_is_guarded(hermes_python: Path, tmp_path: Path) -> None:
    """Hermes' ``handle_function_call`` with ClaimCoach enabled, a leaking handler, a live worker.

    Without a raising hook the agent gets the guarded result; with a raising hook Hermes fails
    open (PC-7) and the agent still gets the handler-redacted result.
    """
    port = free_port_in_range(18200, 18201)  # the gateway's default worker port
    home = tmp_path / "hermes-home"
    (home / "plugins").mkdir(parents=True)
    (home / "plugins" / "claimcoach").symlink_to(PLUGIN_DIR, target_is_directory=True)
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": ["claimcoach"]}}))
    token = home / "plugin-data" / "claimcoach" / "worker" / "token"
    token.parent.mkdir(parents=True)
    token.write_text(TOKEN)
    case_file = tmp_path / "case.json"
    case_file.write_text(case_result())
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONPATH": str(HERMES_ROOT)}
    with FakeModelServer() as phi_model:
        serve_phi(phi_model, fake_phi_reply(CASE))
        app = create_app(TOKEN, redactor=Redactor(PhiDetector(static_models(phi_model.base_url))))
        with LiveApp(app, port=port):
            completed = subprocess.run(
                [
                    str(hermes_python),
                    str(REPO_ROOT / "tests/hermes/probe_guard.py"),
                    str(PLUGIN_DIR),
                    str(case_file),
                ],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=True,
            )
    probe = json.loads(completed.stdout.strip().splitlines()[-1])
    assert probe["hooks"] == 1
    for key in ("handler", "failing_hook"):
        assert leaked(probe[key]) == [], key
        assert "[NAME]" in json.loads(probe[key])["summary"], key
