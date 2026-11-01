"""Helpers for EPIC-12 tests: an eval-ready worker over fake models, and models that read prompts.

Implements: US-12.1 to US-12.4 test harness (ES-4: offline; one fake OpenAI-compatible server per
model role, a corpus over a temporary Hermes root with code notes, rule cards, and letter
templates). ``perfect_classifier`` answers the label each case's reason code signals, and
``letter_reader`` reads a denial letter's codes from its text, as good models would; the EOB PDF
reading is a fixed reply (the fake cannot see the page image), so PDF cases read as CO-197.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx
import pytest
from fastapi import FastAPI

from claimcoach.api.client import WorkerClient
from claimcoach.cases.diagnosis import DenialReason
from claimcoach.corpus.service import CorpusService
from claimcoach.egress import EgressStatus
from claimcoach.evals.datasets import DenialEvalSet, load_denial_set
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.manager import ModelManager
from claimcoach.models.types import ModelRole
from claimcoach.paths import app_data_dir
from claimcoach.redact.detector import PhiDetector
from claimcoach.redact.redactor import Redactor
from claimcoach.worker.app import create_app, get_egress_status
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.launcher import worker_status
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.diagnosis import CODE_BUNDLE, RULE_BUNDLE, explanation_reply, role_models
from tests.fakes.drafting import TEMPLATE_BUNDLE, letter_reply
from tests.fakes.eob import EOB_READING, eob_reply
from tests.fakes.fake_model_server import ChatRequest, FakeModelServer
from tests.fakes.phi import static_models
from tests.fixtures.denials.generate import CODES, FIXTURE_PATH

__all__ = [
    "DENIAL_SET",
    "EvalWorker",
    "connect_to",
    "eval_worker",
    "letter_reader",
    "perfect_classifier",
    "prompt_text",
    "running_worker_port",
    "subset",
]

DENIAL_SET: Final = load_denial_set(FIXTURE_PATH)
CARC_REASON: Final = {carc: reason for reason, codes in CODES.items() for _group, carc in codes}
_CARC: Final = re.compile(r'"carc":\s*"(\d+)"')
_LETTER_CODES: Final = re.compile(r"group code (\w+) and reason code (\d+)")


def prompt_text(request: ChatRequest) -> str:
    """Every text part of the request's messages, in order."""
    parts: list[str] = []
    for message in request.messages:
        if isinstance(message.content, str):
            parts.append(message.content)
        else:
            parts += [str(part.get("text", "")) for part in message.content]
    return "\n".join(parts)


def perfect_classifier(request: ChatRequest) -> str:
    """Answer the family the reason code in the case facts signals."""
    codes = _CARC.findall(prompt_text(request))
    reason = CARC_REASON.get(codes[-1], DenialReason.OTHER) if codes else DenialReason.OTHER
    return json.dumps(
        {"denial_reason": reason.value, "appeal_likelihood": "medium", "reasons": ["Synthetic."]}
    )


def letter_reader(request: ChatRequest) -> str:
    """Read a denial letter's group and reason code; anything else reads as the EOB page."""
    found = _LETTER_CODES.search(prompt_text(request))
    if found is None:
        return eob_reply()
    line = dict(EOB_READING["lines"][0])
    line["adjustments"] = [{"group_code": found[1], "carc": found[2], "amount": "250.00"}]
    line["rarc_codes"] = []
    return eob_reply(lines=[line])


def subset(denial_set: DenialEvalSet, *kinds: str) -> DenialEvalSet:
    """The cases whose documents are all of ``kinds``."""
    cases = [c for c in denial_set.cases if set(c.kinds) <= set(kinds)]
    return denial_set.model_copy(update={"cases": cases})


@dataclass
class EvalWorker:
    """A worker app over fake models and a temporary corpus, ready for every eval."""

    app: FastAPI
    service: CorpusService
    servers: dict[ModelRole, FakeModelServer]

    def client(self) -> WorkerClient:
        """A worker client over the app, in process."""
        return WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(self.app))


def connect_to(worker: EvalWorker) -> Callable[[int], WorkerClient]:
    """``main``'s ``connect`` for the eval worker, whatever port is asked for."""
    return lambda _port: worker.client()


@contextmanager
def eval_worker(
    root: Path,
    corpus_server: FakeModelServer,
    *,
    phi_reply: str = '{"spans": []}',
    models: ModelManager | None = None,
    egress: EgressStatus | None = None,
) -> Iterator[EvalWorker]:
    """Serve a worker whose roles are fake servers and whose corpus can diagnose and draft.

    Args:
        root: The Hermes root of the corpus.
        corpus_server: The fake embedding server.
        phi_reply: What the PHI model answers (``/redact``).
        models: A model manager for ``/models`` (the egress preconditions); none by default.
        egress: What ``GET /egress`` answers; by default a recording audit with nothing dropped,
            as a worker started by ``python -m claimcoach.worker`` answers.
    """
    servers = {
        ModelRole.EXTRACTION: FakeModelServer(),
        ModelRole.CLASSIFICATION: FakeModelServer(),
        ModelRole.EXPLANATION: FakeModelServer({DEFAULT_MODEL_ID: explanation_reply()}),
        ModelRole.DRAFTING: FakeModelServer({DEFAULT_MODEL_ID: letter_reply()}),
        ModelRole.PHI_DETECTION: FakeModelServer({DEFAULT_MODEL_ID: phi_reply}),
    }
    servers[ModelRole.EXTRACTION].responders[DEFAULT_MODEL_ID] = letter_reader
    servers[ModelRole.CLASSIFICATION].responders[DEFAULT_MODEL_ID] = perfect_classifier
    for server in servers.values():
        server.start()
    service = make_service(root, corpus_server)
    try:
        for bundle in (CODE_BUNDLE, RULE_BUNDLE, TEMPLATE_BUNDLE):
            asyncio.run(service.import_bundle(bundle))
        phi = PhiDetector(static_models(servers[ModelRole.PHI_DETECTION].base_url))
        app = create_app(
            TOKEN,
            models,
            redactor=Redactor(phi),
            corpus=service,
            pipeline_models=role_models({role: s.base_url for role, s in servers.items()}),
        )
        status = egress or EgressStatus(audit=True, dropped=0)
        app.dependency_overrides[get_egress_status] = lambda: status
        yield EvalWorker(app=app, service=service, servers=servers)
    finally:
        service.close()
        for server in servers.values():
            server.stop()


def running_worker_port() -> int:
    """The port of the running worker (``WORKER_PORT``, default 18200); skips when none runs."""
    port = int(os.environ.get("WORKER_PORT", "18200"))
    if worker_status(WorkerConfig(data_dir=app_data_dir(), port=port)) is None:
        pytest.skip(f"no ClaimCoach worker on port {port}; start it with make start")
    return port
