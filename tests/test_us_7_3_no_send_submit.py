"""US-7.3 No Send or Submit Anywhere (Python half).

Scenarios: no backend route transmits case content; a case's routes reach only loopback. Also: the
pinned route tables, the source scan for mail and HTTP clients, and BR-4 in the docstrings. The
contribution scenario runs under ``node --test`` (``plugin/desktop/tests/appeal_draft.test.mjs``,
``test_us_7_3_no_send_contribution``).
Rules: BR-1, BR-2, BR-4, NFR-5.
"""

from __future__ import annotations

import ast
import asyncio
import re
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final, NamedTuple

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Mount, Route, WebSocketRoute

from claimcoach.api import relay, routes
from claimcoach.api.client import WorkerClient
from claimcoach.corpus.service import CorpusService
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.manager import ModelManager
from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry
from claimcoach.models.types import DownloadRequest, ModelRole
from claimcoach.worker.app import create_app
from claimcoach.worker.config import LOOPBACK, WorkerConfig
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.corrections import drafting_responder
from tests.fakes.diagnosis import (
    CODE_BUNDLE,
    RULE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
)
from tests.fakes.drafting import TEMPLATE_BUNDLE, letter_reply
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.socket_guard import is_loopback
from tests.test_us_5_1_case_intake import ERA_835, hermes_multipart
from tests.test_us_6_1_diagnosis import PREFIX

PLUGIN: Final = Path(__file__).resolve().parents[1] / "plugin"
APP: Final = PLUGIN / "claimcoach"

SEND: Final = re.compile(
    r"send|sent|submit|fax|e-?mail|mail|smtp|transmit|deliver|forward|upload-to|payer", re.I
)
"""What a route that sends something to a payer would be called."""

GATEWAY_ROUTES: Final = {
    ("GET", "/health"),
    ("GET", "/settings"),
    # US-10.3: the retention period goes to this profile's config.yaml through Hermes' writer.
    ("POST", "/settings/retention"),
    ("GET", "/corpus/status"),
    # US-10.4: a local bundle file is previewed, then imported into the global corpus on confirm.
    ("POST", "/corpus/import/preview"),
    ("POST", "/corpus/import"),
    ("GET", "/models/status"),
    ("POST", "/models/download"),
    ("POST", "/cases"),
    ("GET", "/cases"),
    ("GET", "/cases/{case_id}"),
    ("POST", "/cases/{case_id}/documents"),
    ("POST", "/cases/{case_id}/paste"),
    ("POST", "/cases/{case_id}/process"),
    ("POST", "/cases/{case_id}/diagnose"),
    ("POST", "/cases/{case_id}/draft"),
    ("POST", "/cases/{case_id}/draft/text"),
    ("POST", "/cases/{case_id}/export"),
    ("POST", "/cases/{case_id}/correction"),
    ("POST", "/cases/{case_id}/correction/export"),
    ("POST", "/cases/{case_id}/outcome"),
    ("POST", "/cases/{case_id}/fields"),
    ("GET", "/outcomes/summary"),
    ("POST", "/outcomes/export"),
    # US-11.1: a recording is stored in the case and queued for local transcription; nothing sent.
    ("POST", "/cases/{case_id}/calls"),
    ("POST", "/cases/{case_id}/calls/{call_id}/transcribe"),
}
"""Every ``plugin_api.py`` route; each proxies to the loopback worker. Review before changing."""

WORKER_ROUTES: Final = {
    ("GET", "/health"),
    ("GET", "/egress"),  # US-12.4: the audit's state only, no record
    ("GET", "/models/status"),
    ("POST", "/models/{role}/load"),
    ("POST", "/models/{role}/unload"),
    ("POST", "/models/download"),
    ("POST", "/redact"),
    ("GET", "/corpus/status"),
    ("POST", "/corpus/import"),
    ("GET", "/corpus/global"),
    ("POST", "/corpus/reindex"),
    ("POST", "/corpus/purge"),
    ("GET", "/corpus/audit"),
    ("POST", "/cases"),
    ("GET", "/cases"),
    ("GET", "/cases/{case_id}"),
    ("POST", "/cases/{case_id}/documents"),
    ("POST", "/cases/{case_id}/paste"),
    ("POST", "/cases/{case_id}/extract"),
    ("POST", "/cases/{case_id}/diagnose"),
    ("POST", "/cases/{case_id}/draft"),
    ("POST", "/cases/{case_id}/draft/text"),
    ("POST", "/cases/{case_id}/export"),
    ("POST", "/cases/{case_id}/correction"),
    ("POST", "/cases/{case_id}/correction/export"),
    ("POST", "/cases/{case_id}/outcome"),
    ("POST", "/cases/{case_id}/fields"),
    ("GET", "/jobs/{job_id}/events"),
    ("GET", "/outcomes/summary"),
    ("POST", "/outcomes/export"),
    # US-9.1, US-9.2: the agent tools' answers; they read the global corpus and one case only.
    ("POST", "/agent/explain-code"),
    ("POST", "/agent/rule-cards"),
    ("POST", "/agent/case-summary"),
    # US-11.1: recordings, the local transcription queue, and its PHI-free listing.
    ("POST", "/cases/{case_id}/calls"),
    ("POST", "/cases/{case_id}/calls/{call_id}/transcribe"),
    ("GET", "/transcriptions"),
}
"""Every worker route with every optional part mounted. Review before changing."""

OUTBOUND_ROUTES: Final = {("POST", "/models/download")}
"""The only routes whose work may leave this Mac (BR-1: a user-confirmed model download)."""

HTTP_CLIENT_MODULES: Final = {
    "claimcoach/api/client.py": "the gateway's client of the worker (WorkerConfig: 127.0.0.1)",
    "claimcoach/models/chat.py": "chat completions to a ModelEndpoint (127.0.0.1)",
    "claimcoach/models/manager.py": "model servers' health checks (127.0.0.1)",
    "claimcoach/corpus/embed.py": "embeddings from a ModelEndpoint (127.0.0.1)",
    "claimcoach/worker/launcher.py": "the worker's /health (WorkerConfig: 127.0.0.1)",
    "claimcoach/calls/transcribe.py": "audio transcription to a ModelEndpoint (127.0.0.1)",
    "claimcoach/evals/flow.py": "the plugin_api router mounted in-process (ASGITransport, US-12.4)",
}
"""The reviewed modules that create HTTP clients, and the loopback service each one talks to."""

PROCESS_MODULES: Final = {
    "claimcoach/corpus/crypto.py": "macOS `security` for the Keychain key (fixed argv)",
    "claimcoach/models/acquire.py": "`hf download`, `mlx_lm.convert` once the user confirms (BR-1)",
    "claimcoach/models/manager.py": "the local model servers and `ps` for their command lines",
    "claimcoach/worker/launcher.py": "the worker itself and `ps` for its command line",
    "claimcoach/evals/egress_check.py": "`lsof -nP` on the worker and model-server PIDs (US-12.4)",
}
"""The reviewed modules that start processes; none passes case content in its argv."""

SOCKET_MODULES: Final = {"claimcoach/models/manager.py": "a free-port probe on 127.0.0.1"}
"""The reviewed modules that open sockets directly."""

JS_SURFACES: Final = (
    r"\bfetch\(",
    "XMLHttpRequest",
    "WebSocket",
    "EventSource",
    "sendBeacon",
    r"window\.open",
    "openExternal",
    r"location\.(href|assign|replace)",
    r"navigator\.share",
    r"\bimport\(",
    "mailto:",
    r"https?://",
)
"""Ways a browser page sends something; plugin.js reaches its backend through ctx.rest only."""

FORBIDDEN_IMPORTS: Final = frozenset(
    {
        "smtplib",
        "imaplib",
        "poplib",
        "ftplib",
        "telnetlib",
        "urllib.request",
        "http.client",
        "requests",
        "aiohttp",
        "urllib3",
        "webbrowser",
        "email.mime",
        "xmlrpc.client",
    }
)
"""Mail, FTP, raw HTTP, and browser clients: none belongs in a local-only app (BR-4, NFR-5)."""


def _api_routes(app_routes: list[Any]) -> Iterator[APIRoute]:
    """Every ``APIRoute``, inside included routers too (FastAPI wraps an included router)."""
    for route in app_routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _api_routes(route.original_router.routes)


def _routes(app_routes: list[Any], prefix: str = "") -> set[tuple[str, str]]:
    """Every route as ``(method, path)``; websockets as ``WS``. Any other route type fails."""
    found: set[tuple[str, str]] = set()
    for route in app_routes:
        if isinstance(route, APIRoute | Route):
            found |= {(m, prefix + route.path) for m in route.methods or ()}
        elif isinstance(route, APIWebSocketRoute | WebSocketRoute):
            found.add(("WS", prefix + route.path))
        elif isinstance(route, Mount):
            found |= _routes(route.routes, prefix + route.path)
        elif hasattr(route, "original_router"):
            found |= _routes(route.original_router.routes, prefix)
        else:
            pytest.fail(f"unknown route type {type(route).__name__}: review it for BR-4")
    return found


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


# --- Scenario: No backend route transmits case content -------------------------------------------


def test_us_7_3_no_transmitting_route(service: CorpusService, tmp_path: Path) -> None:
    gateway = _routes(routes.router.routes)
    manager = ModelManager(
        ModelRegistry.load(DEFAULT_REGISTRY),
        models_home=tmp_path / "models",
        state_dir=tmp_path / "state",
    )
    worker = _routes(create_app(TOKEN, manager, corpus=service).routes)

    assert gateway == GATEWAY_ROUTES, "a new gateway route: review it for BR-4, then pin it"
    assert worker == WORKER_ROUTES, "a new worker route: review it for BR-4, then pin it"
    for method, path in gateway | worker:
        assert not SEND.search(path), f"{method} {path} is named like a send"
    names = {
        route.endpoint.__name__
        for app_routes in (routes.router.routes, create_app(TOKEN, manager, corpus=service).routes)
        for route in _api_routes(app_routes)
    }
    assert len(names) >= 20
    assert not [name for name in names if SEND.search(name)]
    # The gateway only proxies: every route reaches the worker on 127.0.0.1.
    assert WorkerConfig(data_dir=tmp_path).base_url.startswith("http://127.0.0.1:")
    # The one outbound route carries no case content: a role and a yes/no answer only.
    assert worker >= OUTBOUND_ROUTES
    assert set(DownloadRequest.model_fields) == {"role", "confirm"}
    assert DownloadRequest.model_fields["role"].annotation is ModelRole


def test_us_7_3_the_route_walk_sees_every_route_type() -> None:
    """A Starlette route, a websocket, and a mounted app are enumerated too, never skipped."""

    async def endpoint(_request: Any) -> Any: ...

    sub = FastAPI()
    sub.add_api_route("/fax", endpoint, methods=["POST"])
    probe = FastAPI()
    probe.add_route("/cases/{case_id}/submit", endpoint, methods=["POST"])
    probe.add_api_websocket_route("/cases/{case_id}/send", endpoint)
    probe.mount("/outbox", sub)
    found = _routes(probe.routes)
    assert {("POST", "/cases/{case_id}/submit"), ("WS", "/cases/{case_id}/send")} <= found
    assert ("POST", "/outbox/fax") in found
    sends = {
        ("POST", "/cases/{case_id}/submit"),
        ("WS", "/cases/{case_id}/send"),
        ("POST", "/outbox/fax"),
    }
    assert all(SEND.search(path) for _method, path in sends)
    with pytest.raises(pytest.fail.Exception):
        _routes([object()])


async def test_us_7_3_case_routes_reach_only_loopback(
    service: CorpusService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every case route with case content, end to end; record every socket connect.

    Upload, paste, extract, confirm, diagnose, draft, edit, export, draft and export the corrected
    claim (US-7.4), and open, through the gateway
    (the relay reads ``/jobs/{job_id}/events``). The worker's ``/redact`` is the PHI model's
    loopback call (US-3.1) and is not reachable from the gateway.
    """
    for bundle in (CODE_BUNDLE, RULE_BUNDLE, TEMPLATE_BUNDLE):
        await service.import_bundle(bundle)
    replies = {
        ModelRole.CLASSIFICATION: classification_reply(),
        ModelRole.EXPLANATION: explanation_reply(),
        ModelRole.DRAFTING: letter_reply(),
    }
    servers = [FakeModelServer(replies={DEFAULT_MODEL_ID: r}).start() for r in replies.values()]
    servers[-1].responders[DEFAULT_MODEL_ID] = drafting_responder()  # the letter and the changes
    connects: list[Any] = []
    lookups: list[Any] = []
    real_connect, real_getaddrinfo = socket.socket.connect, socket.getaddrinfo

    def connect(sock: socket.socket, address: Any) -> None:
        connects.append(address)
        real_connect(sock, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        lookups.append(host)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    try:
        models = role_models(dict(zip(replies, (s.base_url for s in servers), strict=True)))
        worker = create_app(TOKEN, corpus=service, pipeline_models=models)
        client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
        gateway = FastAPI()
        gateway.include_router(routes.router, prefix=PREFIX)
        gateway.dependency_overrides[routes.get_worker_client] = lambda: client
        gateway.dependency_overrides[routes.get_event_sink] = lambda: lambda *_: None
        transport = httpx.ASGITransport(app=gateway)
        async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
            case_id = (await desktop.post(f"{PREFIX}/cases", json={})).json()["case_id"]
            calls = [
                ("paste", {"text": ERA_835}),
                ("process", {}),
                ("fields", {"path": "claim_id", "value": "CLAIM-77"}),
                ("diagnose", {}),
                ("draft", {}),
                ("draft/text", {"text": "Edited letter."}),
                ("export", {"format": "pdf"}),
                ("export", {"format": "docx"}),
                ("correction", {}),
                ("correction/export", {"format": "pdf"}),
            ]
            for action, body in calls:
                response = await desktop.post(f"{PREFIX}/cases/{case_id}/{action}", json=body)
                assert response.status_code == 200, (action, response.text)
                await asyncio.gather(*relay._RELAYS.values())
            upload, content_type = hermes_multipart("letter.txt", "text/plain", b"Denial letter.")
            uploaded = await desktop.post(
                f"{PREFIX}/cases/{case_id}/documents",
                content=upload,
                headers={"content-type": content_type},
            )
            assert uploaded.status_code == 200, uploaded.text
            assert (await desktop.get(f"{PREFIX}/cases/{case_id}")).json()["draft"]["text"] == (
                "Edited letter."
            )
    finally:
        for server in servers:
            server.stop()
    hosts = [address[0] for address in connects if isinstance(address, tuple)]
    assert len(hosts) >= 3, "the three model roles were called over sockets"
    assert all(is_loopback(host) for host in hosts), hosts
    assert all(is_loopback(host) for host in lookups), lookups


# --- The source: mail and HTTP clients ------------------------------------------------------------


def _python_modules() -> Iterator[Path]:
    yield from sorted(PLUGIN.rglob("*.py"))


_CLIENTS: Final = frozenset({"AsyncClient", "Client", "get", "post", "put", "request", "stream"})
_PROCESS_CALLS: Final = frozenset(
    {"create_subprocess_exec", "create_subprocess_shell", "system", "popen", "posix_spawn"}
)
_SOCKET_CALLS: Final = frozenset(
    {"socket", "create_connection", "open_connection", "create_datagram_endpoint"}
)


class Scan(NamedTuple):
    """What one module's source can do to reach outside the process."""

    forbidden: set[str]
    http: bool
    processes: bool
    sockets: bool
    dynamic_imports: bool


def scan(source: str) -> Scan:
    """Scan one module: forbidden imports, HTTP clients, subprocesses, sockets, dynamic imports.

    ``import httpx as hx`` and ``from httpx import AsyncClient`` count as HTTP clients;
    ``from http import client`` counts as ``http.client``.
    """
    tree = ast.parse(source)
    imported: set[str] = set()
    httpx_names: set[str] = set()  # names bound to the httpx module
    httpx_callables: set[str] = set()  # names bound to httpx clients or request functions
    found = Scan(set(), http=False, processes=False, sockets=False, dynamic_imports=False)
    flags = found._asdict()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
                if alias.name == "httpx":
                    httpx_names.add(alias.asname or "httpx")
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
            if node.module == "httpx":
                httpx_callables.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                flags["http"] |= func.id in httpx_callables
                flags["dynamic_imports"] |= func.id == "__import__"
            elif isinstance(func, ast.Attribute):
                owner = func.value.id if isinstance(func.value, ast.Name) else None
                flags["http"] |= owner in httpx_names and func.attr in _CLIENTS
                flags["processes"] |= owner == "subprocess" or func.attr in _PROCESS_CALLS
                flags["processes"] |= owner == "os" and func.attr.startswith(("exec", "spawn"))
                flags["sockets"] |= owner in {"socket", "asyncio"} and func.attr in _SOCKET_CALLS
                flags["dynamic_imports"] |= func.attr == "import_module"
    flags["forbidden"] = {
        name
        for name in imported
        for bad in FORBIDDEN_IMPORTS
        if name == bad or name.startswith(f"{bad}.")
    }
    return Scan(**flags)


def test_us_7_3_http_clients_only_in_loopback_modules() -> None:
    reached: dict[str, set[str]] = {"http": set(), "processes": set(), "sockets": set()}
    for path in _python_modules():
        name = path.relative_to(PLUGIN).as_posix()
        found = scan(path.read_text())
        assert not found.forbidden, f"{name} imports {sorted(found.forbidden)}"
        assert not found.dynamic_imports, f"{name} imports a module by name at run time"
        for kind, modules in reached.items():
            if getattr(found, kind):
                modules.add(name)
    assert reached["http"] == set(HTTP_CLIENT_MODULES), "a new HTTP client: review where it goes"
    assert reached["processes"] == set(PROCESS_MODULES), "a new subprocess: review its argv"
    assert reached["sockets"] == set(SOCKET_MODULES), "a new socket: review where it connects"
    # Model endpoints are always loopback: every ModelEndpoint is built on LOOPBACK.
    assert LOOPBACK == "127.0.0.1"
    endpoints = [
        node
        for path in _python_modules()
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ModelEndpoint"
    ]
    assert endpoints, "the scan found where endpoints are built"
    for call in endpoints:
        (url,) = [k.value for k in call.keywords if k.arg == "base_url"]
        assert isinstance(url, ast.JoinedStr)
        scheme, host = url.values[:2]
        assert isinstance(scheme, ast.Constant)
        assert scheme.value == "http://"
        assert isinstance(host, ast.FormattedValue)
        assert isinstance(host.value, ast.Name)
        assert host.value.id == "LOOPBACK"
    js = re.sub(
        r"/\*[\s\S]*?\*/|//.*$", "", (PLUGIN / "desktop" / "plugin.js").read_text(), flags=re.M
    )
    for surface in JS_SURFACES:
        assert not re.search(surface, js), f"plugin.js uses {surface}"


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("import smtplib", "forbidden"),
        ("from http import client", "forbidden"),
        ("from urllib import request", "forbidden"),
        ("from email import mime", "forbidden"),
        ("from urllib.request import urlopen", "forbidden"),
        ("from httpx import AsyncClient\nAsyncClient()", "http"),
        ("import httpx as hx\nhx.post('https://payer.example')", "http"),
        ("import asyncio\nasyncio.open_connection('payer.example', 443)", "sockets"),
        ("import socket\nsocket.create_connection(('payer.example', 25))", "sockets"),
        ("import subprocess\nsubprocess.run(['curl', '-F', 'f=@x.pdf', 'https://p'])", "processes"),
        ("import os\nos.system('lp letter.pdf')", "processes"),
        ("import os\nos.execvp('osascript', ['osascript'])", "processes"),
        ("import importlib\nimportlib.import_module('smtplib')", "dynamic_imports"),
        ("__import__('smtplib')", "dynamic_imports"),
    ],
)
def test_us_7_3_the_scan_catches_a_way_out(source: str, kind: str) -> None:
    found = scan(source)
    assert getattr(found, kind), f"{source!r} was not caught"
    assert SEND.search("/cases/{case_id}/submit")
    assert SEND.search("send_to_payer")


def test_us_7_3_the_scan_passes_plain_code() -> None:
    assert scan("import json\nimport httpx\njson.dumps({})\nhttpx.HTTPError") == Scan(
        set(), http=False, processes=False, sockets=False, dynamic_imports=False
    )


# --- BR-4 is documented where it holds ----------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "claimcoach/api/routes.py",
        "claimcoach/worker/case_routes.py",
        *(p.relative_to(PLUGIN).as_posix() for p in sorted((APP / "letters").glob("*.py"))),
    ],
)
def test_us_7_3_docstrings_cite_br_4(path: str) -> None:
    docstring = ast.get_docstring(ast.parse((PLUGIN / path).read_text()))
    assert docstring is not None
    assert "BR-4" in docstring


def test_us_7_3_plugin_js_header_cites_br_4() -> None:
    header = (PLUGIN / "desktop" / "plugin.js").read_text().split("*/", 1)[0]
    assert "BR-4" in header
    assert "US-7.3" in header
