"""The worker's corpus: both scopes' stores, opened once and shared by every request.

Implements: US-4.1 (status and reindex), US-4.2 (user stores open with the profile's Keychain
key), US-4.3 (import and the global view), US-4.4 (a ``Retriever`` per profile), US-4.5 (purge,
scheduled over every profile), US-4.6 (audit). Rules: BR-5, BR-6, BR-7, BR-13, PC-4 (all of this
runs in the worker), BR-14 (a failing profile is logged by error type only).

The worker is app-wide, so a user scope is addressed by profile name (``paths.profile_user_
scope_dir``); stores stay open until ``close``. Reads never create a user scope: only case
creation (``create=True``, US-5.1) does, so a mistyped profile name leaves no directory and no
Keychain item behind. Opening a store may call the Keychain, so routes run it off the event loop.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from claimcoach.corpus.bundle import CorpusBundle, CorpusViewResponse, ImportResult
from claimcoach.corpus.crypto import Cipher, KeyProvider, key_account
from claimcoach.corpus.embed import Embedder, Reranker
from claimcoach.corpus.errors import CorpusError, ProfileNotFoundError
from claimcoach.corpus.importer import corpus_view, import_bundle
from claimcoach.corpus.paths import (
    DATABASE,
    global_scope_dir,
    profile_home,
    profile_user_scope_dir,
    user_scopes,
)
from claimcoach.corpus.retention import RetentionPolicy, purge_case, purge_expired
from claimcoach.corpus.retrieve import Retriever
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import (
    AuditResponse,
    CorpusScope,
    CorpusStatusResponse,
    PurgeReport,
    PurgeRequest,
    PurgeResponse,
    ReindexRequest,
    ReindexResult,
    ScopeStatus,
)
from claimcoach.logs import get_logger

__all__ = ["CorpusService"]

_log = get_logger("claimcoach.corpus")


class CorpusService:
    """Both scopes for every profile under one Hermes root.

    Args:
        root: The Hermes root.
        keys: Supplies each profile's user-store key (the Keychain in the worker).
        embedder: Embeds documents and queries (the ``embedding`` role).
        reranker: Scores retrieval candidates (the ``rerank`` role).
        embedding_model_id: The embedding model ``models.yaml`` configures now.
    """

    def __init__(
        self,
        root: Path,
        keys: KeyProvider,
        embedder: Embedder,
        reranker: Reranker,
        *,
        embedding_model_id: str,
    ) -> None:
        """Hold the settings; no store opens until it is first used."""
        self.root = root
        self.embedding_model_id = embedding_model_id
        self.embedder = embedder
        self.reranker = reranker
        self._keys = keys
        self._global: CorpusStore | None = None
        self._users: dict[str, CorpusStore] = {}
        self._open_lock = threading.Lock()  # routes and the purge thread open stores
        self._writes = asyncio.Lock()  # one import or reindex at a time

    def global_store(self) -> CorpusStore:
        """Return the global scope's store."""
        with self._open_lock:
            if self._global is None:
                self._global = CorpusStore(
                    global_scope_dir(self.root),
                    CorpusScope.GLOBAL,
                    embedding_model_id=self.embedding_model_id,
                )
            return self._global

    def user_store(self, profile: str, *, create: bool = False) -> CorpusStore:
        """Return ``profile``'s user scope, opened with its Keychain key.

        Args:
            profile: Hermes profile name.
            create: Create the scope (and its key) when it does not exist yet; case creation only.

        Raises:
            InvalidProfileError: ``profile`` is not a Hermes profile name.
            ProfileNotFoundError: The scope does not exist and ``create`` is false.
            CorpusKeyError: The key is unavailable or does not decrypt the store. An existing
                store never gets a new key.
        """
        with self._open_lock:
            store = self._users.get(profile)
            if store is None:
                directory = profile_user_scope_dir(profile, self.root, create=False)
                exists = (directory / DATABASE).is_file()
                if not exists and not create:
                    raise ProfileNotFoundError
                key = self._keys.key_for(key_account(profile), create=not exists)
                store = CorpusStore(
                    profile_user_scope_dir(profile, self.root),
                    CorpusScope.USER,
                    embedding_model_id=self.embedding_model_id,
                    cipher=Cipher(key),
                    profile=profile,
                )
                self._users[profile] = store
            return store

    def _store(self, scope: CorpusScope, profile: str) -> CorpusStore:
        return self.global_store() if scope is CorpusScope.GLOBAL else self.user_store(profile)

    def _user_status(self, profile: str, directory: Path) -> ScopeStatus:
        try:
            return self.user_store(profile).status()
        except CorpusError as exc:
            _log.warning("a profile's user scope did not open: %s", type(exc).__name__)
            return ScopeStatus(
                scope=CorpusScope.USER,
                profile=profile,
                path=str(directory),
                available=False,
                encrypted=True,
            )

    def status(self) -> CorpusStatusResponse:
        """Return both scopes' status; a user scope that does not open is ``available: false``."""
        return CorpusStatusResponse(
            global_scope=self.global_store().status(),
            user_scopes=[
                self._user_status(profile, directory)
                for profile, directory in user_scopes(self.root).items()
            ],
        )

    async def import_bundle(self, bundle: CorpusBundle) -> ImportResult:
        """Import ``bundle`` into the global scope (all or nothing)."""
        async with self._writes:
            return await import_bundle(self.global_store(), bundle, self.embedder)

    def view(self, today: date | None = None) -> CorpusViewResponse:
        """Return the global corpus view, judged stale against the local date."""
        return corpus_view(self.global_store(), today or date.today())

    async def reindex(self, request: ReindexRequest) -> ReindexResult:
        """Re-embed every chunk of one scope under the configured embedding model.

        Raises:
            ProfileNotFoundError: A user scope that does not exist.
        """
        async with self._writes:
            store = await asyncio.to_thread(self._store, request.scope, request.profile)
            items = store.reindex_items()
            vectors = await self.embedder.embed_documents([text for _, text in items])
            store.replace_index([chunk_id for chunk_id, _ in items], vectors)
        return ReindexResult(chunks=len(items), embedding_model_id=self.embedding_model_id)

    def retriever(self, profile: str) -> Retriever:
        """Return a retriever over the global scope and ``profile``'s user scope."""
        user = self.user_store(profile)
        return Retriever(self.global_store(), user, self.embedder, self.reranker)

    def purge(self, request: PurgeRequest, now: datetime | None = None) -> PurgeResponse:
        """Purge one case on request, one profile's expired cases, or every profile's.

        Raises:
            CaseNotFoundError: A single-case purge names an unknown case.
            ProfileNotFoundError: A named profile has no user scope.
            CorpusError: A named profile's store cannot be opened.
        """
        if request.profile is None:
            return self.purge_all(now)
        store = self.user_store(request.profile)
        if request.case_id is not None:
            return PurgeResponse(reports=[purge_case(store, request.case_id, now)])
        report = self._purge_profile(request.profile, now)
        if report is None:
            return PurgeResponse(reports=[], skipped=[request.profile])
        return PurgeResponse(reports=[report])

    def _purge_profile(self, profile: str, now: datetime | None) -> PurgeReport | None:
        policy = RetentionPolicy.for_profile(profile_home(profile, self.root))
        if policy is None:
            return None  # retention setting unreadable: keep everything until the next run
        return purge_expired(self.user_store(profile), policy, now)

    def purge_all(self, now: datetime | None = None) -> PurgeResponse:
        """Purge every profile's expired cases; one profile's failure does not stop the rest."""
        reports, skipped = [], []
        for profile in user_scopes(self.root):
            try:
                report = self._purge_profile(profile, now)
            except (CorpusError, sqlite3.Error, ValidationError) as exc:
                _log.error("retention purge skipped a profile: %s", type(exc).__name__)
                report = None
            if report is None:
                skipped.append(profile)
            else:
                reports.append(report)
        return PurgeResponse(reports=reports, skipped=skipped)

    def audit(self, profile: str, case_id: str | None = None) -> AuditResponse:
        """Return ``profile``'s audit entries, only ``case_id``'s when given.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
        """
        return AuditResponse(entries=self.user_store(profile).audit_log(case_id))

    def close(self) -> None:
        """Close every open store."""
        with self._open_lock:
            stores = [*self._users.values(), *([self._global] if self._global else [])]
            self._users.clear()
            self._global = None
        for store in stores:
            store.close()
