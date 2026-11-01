"""Helpers for agent-integration tests: a live worker behind the tools, and diagnosed cases.

Implements: US-9.1 to US-9.4 test harness (ES-4: offline). The worker runs on a real loopback
socket with the real ``/agent`` and ``/redact`` routes, backed by fake models: the guard and the
tools reach it from their own thread and event loop, as they do inside the Hermes gateway.
Nothing here names a person; the PHI comes from ``tests/fixtures/phi``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from claimcoach.agent.guard import Scrubber
from claimcoach.agent.tools import register_agent
from claimcoach.api.client import WorkerClient
from claimcoach.api.models import ERROR_MESSAGES, ErrorCode
from claimcoach.cases.extraction import FieldConfirmation
from claimcoach.cases.service import CaseService
from claimcoach.corpus.service import CorpusService
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.diagnose import Diagnoser
from claimcoach.pipeline.extract import Extractor
from claimcoach.redact.detector import PhiDetector
from claimcoach.redact.redactor import Redactor
from claimcoach.redact.types import RedactRequest
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN
from tests.fakes.diagnosis import (
    CODE_BUNDLE,
    RULE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
)
from tests.fakes.eob import eob_reply
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.live_app import LiveApp
from tests.fakes.phi import PHI_DOCUMENTS, fake_phi_reply, serve_phi, static_models
from tests.fakes.registrar import FakeRegistrar
from tests.test_us_5_1_case_intake import ERA_835

__all__ = [
    "AgentWorker",
    "agent_worker",
    "assert_envelope",
    "diagnosed_case",
    "pipeline_models",
    "serve_pipeline",
]


def assert_envelope(raw: str, code: ErrorCode) -> None:
    """``raw`` is exactly the fixed envelope of ``code`` (nothing of the input echoed)."""
    assert json.loads(raw) == {
        "ok": False,
        "error": {"code": code, "message": ERROR_MESSAGES[code]},
    }


@dataclass
class AgentWorker:
    """A live worker the tools and the guard reach on ``base_url``."""

    base_url: str
    registrar: FakeRegistrar = field(default_factory=FakeRegistrar)

    def connect(self) -> WorkerClient:
        """A client for this worker (the tools' ``connect``)."""
        return WorkerClient(self.base_url, lambda: TOKEN, timeout=20)

    @property
    def scrubber(self) -> Scrubber:
        """The guard's redaction call, over this worker's ``/redact``."""

        async def scrub(text: str) -> str:
            return (await self.connect().redact(RedactRequest(text=text))).text

        return scrub

    def call(self, tool: str, args: dict[str, Any]) -> str:
        """Call a registered tool the way Hermes does."""
        handler = self.registrar.tools[tool]["handler"]
        result: str = handler(args, task_id="t1")
        return result

    def run(self, command: str, raw_args: str = "") -> str:
        """Run a registered slash command the way Hermes does (``fn(raw_args)``)."""
        result: str = self.registrar.commands[command]["handler"](raw_args)
        return result


@contextmanager
def agent_worker(service: CorpusService) -> Iterator[AgentWorker]:
    """Serve the worker over ``service`` with a PHI model that knows the fixture's PHI.

    The tools, hook, skill, and command are registered on ``worker.registrar`` against it.
    """
    with FakeModelServer() as phi_model:
        serve_phi(phi_model, fake_phi_reply(*PHI_DOCUMENTS))
        redactor = Redactor(PhiDetector(static_models(phi_model.base_url)))
        with LiveApp(create_app(TOKEN, redactor=redactor, corpus=service)) as live:
            worker = AgentWorker(live.base_url)
            register_agent(worker.registrar, worker.scrubber, worker.connect)
            yield worker


@contextmanager
def serve_pipeline() -> Iterator[dict[ModelRole, FakeModelServer]]:
    """Fake Qwen3-VL-8B, Qwen3-8B, and Qwen3-14B, each answering its own role's prompt."""
    replies = {
        ModelRole.EXTRACTION: eob_reply(),
        ModelRole.CLASSIFICATION: classification_reply(),
        ModelRole.EXPLANATION: explanation_reply(),
    }
    servers = {role: FakeModelServer(replies={DEFAULT_MODEL_ID: r}) for role, r in replies.items()}
    for server in servers.values():
        server.start()
    try:
        yield servers
    finally:
        for server in servers.values():
            server.stop()


def pipeline_models(servers: dict[ModelRole, FakeModelServer]) -> Any:
    """A ``ModelManager.use`` stand-in over ``serve_pipeline``'s servers."""
    return role_models({role: server.base_url for role, server in servers.items()})


async def diagnosed_case(
    service: CorpusService,
    models: Any,
    phi: str,
    *,
    confirm: dict[str, str] | None = None,
    profile: str = "default",
) -> str:
    """A case of the synthetic 835 plus a document seeded with PHI, extracted and diagnosed."""
    await service.import_bundle(CODE_BUNDLE)
    await service.import_bundle(RULE_BUNDLE)
    cases = CaseService(service)
    case_id = cases.create(profile).case_id
    cases.add_text(profile, case_id, ERA_835)
    cases.add_text(profile, case_id, phi)
    await Extractor(cases, models).run(profile, case_id, lambda _s, _p: None)
    for path, value in (confirm or {}).items():
        cases.confirm_field(profile, case_id, FieldConfirmation(path=path, value=value))
    await Diagnoser(cases, models).run(profile, case_id, lambda _s, _p: None)
    return case_id
