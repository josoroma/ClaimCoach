"""Helpers for PHI tests: a perfect fake PHI model over the synthetic fixture set.

Implements: US-3.1 to US-3.4 test harness (ES-4: offline; the fake OpenAI-compatible server stands
in for Qwen3-8B). The fake "model" reports each document's name and address the way a real model
would (``PhiDocument["model"]``: one line, one spelling, even where the document wraps or
upper-cases them); the structured categories are left to the regex validators.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.manager import ModelEndpoint
from claimcoach.models.types import ModelRole
from tests.fakes.fake_model_server import FakeModelServer
from tests.fixtures.phi.generate import PhiDocument, load

__all__ = [
    "PHI_DOCUMENTS",
    "fake_phi_reply",
    "leaked_strings",
    "seeded_strings",
    "serve_phi",
    "static_models",
]

PHI_DOCUMENTS = load()


def fake_phi_reply(*documents: PhiDocument) -> str:
    """Return the JSON a good PHI model answers for ``documents``.

    Names and addresses in the form a model writes them (one line, one spelling), not
    necessarily as the document lays them out.
    """
    spans = [span for document in documents for span in document["model"]]
    return json.dumps({"spans": spans})


def seeded_strings(*documents: PhiDocument) -> Iterator[str]:
    """Every PHI string seeded into ``documents``."""
    for document in documents:
        for values in document["phi"].values():
            yield from values


def leaked_strings(text: str, *documents: PhiDocument) -> list[str]:
    """Seeded PHI strings that occur in ``text`` as whole words, in any case.

    Whole words, so a seeded two-letter surname ("Li") is not "found" inside "list".
    """
    return [
        value
        for value in seeded_strings(*documents)
        if re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text, re.IGNORECASE)
    ]


def static_models(
    base_url: str,
) -> Callable[[ModelRole], AbstractAsyncContextManager[ModelEndpoint]]:
    """A ``ModelManager.use`` stand-in that always yields ``base_url``."""

    @asynccontextmanager
    async def use(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        yield ModelEndpoint(role=role, base_url=base_url)

    return use


def serve_phi(server: FakeModelServer, reply: str) -> None:
    """Make ``server`` answer the PHI prompt with ``reply``."""
    server.replies[DEFAULT_MODEL_ID] = reply
