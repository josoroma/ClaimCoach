"""US-4.1 Global and User Scope Stores.

Scenarios: global scope resolves under the Hermes root; user scope follows the active profile;
each scope has its own database and vector index. Also: invalid profile names, a model change
forces reindex, the store's guards, chunking, the embedder, the status and reindex routes, and
backup/restore. Rules: BR-5, BR-13, PC-6, PRD §9. Offline: the fake server embeds.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import numpy as np
import pytest
from pydantic import ValidationError

from claimcoach.api.models import ERROR_MESSAGES
from claimcoach.corpus import paths
from claimcoach.corpus.backup import BackupError, backup, restore
from claimcoach.corpus.crypto import Cipher
from claimcoach.corpus.embed import Embedder
from claimcoach.corpus.errors import CaseNotFoundError, CorpusError, IndexStaleError
from claimcoach.corpus.paths import (
    DATABASE,
    INDEX,
    InvalidProfileError,
    active_profile,
    global_scope_dir,
    hermes_root,
    profile_home,
    profile_user_scope_dir,
    user_scope_dir,
    user_scopes,
)
from claimcoach.corpus.store import CorpusStore, split_text
from claimcoach.corpus.types import CorpusScope, Document, ReindexRequest
from claimcoach.models.manager import ModelUnavailableError
from tests.conftest import REPO_ROOT
from tests.fakes.corpus import (
    MODEL_ID,
    TOKEN,
    add_case_document,
    corpus_client,
    make_service,
    vectors_for,
)
from tests.fakes.fake_model_server import EMBED_DIM, FakeModelServer
from tests.fakes.phi import static_models

AUTH = {"Authorization": f"Bearer {TOKEN}"}


def install_hermes(monkeypatch: pytest.MonkeyPatch, root: Path) -> Callable[[str], None]:
    """Fake ``hermes_constants`` and ``plugins.plugin_storage``; returns a profile switcher.

    Mirrors Hermes v0.22.5: a profile's home is ``<root>/profiles/<name>`` (the root itself for
    ``default``), and ``plugin_data_dir(name)`` is ``<home>/plugin-data/<name>``, created.
    """
    state = {"home": root}

    def plugin_data_dir(name: str) -> Path:
        path = state["home"] / "plugin-data" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    constants = ModuleType("hermes_constants")
    constants.get_default_hermes_root = lambda: root  # type: ignore[attr-defined]
    constants.get_hermes_home = lambda: state["home"]  # type: ignore[attr-defined]
    storage = ModuleType("plugins.plugin_storage")
    storage.plugin_data_dir = plugin_data_dir  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    monkeypatch.setitem(sys.modules, "plugins", ModuleType("plugins"))
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", storage)

    def switch(profile: str) -> None:
        state["home"] = root if profile == "default" else root / "profiles" / profile

    return switch


def global_doc(key: str = "aetna", text: str = "Aetna timely filing is 180 days.") -> Document:
    return Document(
        doc_id=f"rule_card:{key}",
        scope=CorpusScope.GLOBAL,
        kind="rule_card",
        title="Timely filing",
        text=text,
        metadata={"key": key, "source": "manual", "verified_on": "2026-09-01"},
    )


def put_global(store: CorpusStore, document: Document) -> None:
    chunks = split_text(document.text)
    store.put_document(document, chunks, vectors_for(chunks))


# --- Scenario: Global scope resolves under the Hermes root --------------------------------------


@pytest.mark.parametrize("profile", ["default", "a", "b"])
def test_us_4_1_global_scope_under_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profile: str
) -> None:
    root = tmp_path / "hermes"
    install_hermes(monkeypatch, root)(profile)
    expected = root / "plugin-data" / "claimcoach" / "global"
    assert global_scope_dir() == expected
    assert hermes_root() == root
    assert expected.stat().st_mode & 0o777 == 0o700


def test_us_4_1_global_scope_under_root_outside_hermes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profiles" / "a"))
    assert global_scope_dir() == (tmp_path / "plugin-data" / "claimcoach" / "global").resolve()
    assert global_scope_dir(tmp_path / "x") == tmp_path / "x/plugin-data/claimcoach/global"


# --- Scenario: User scope follows the active profile --------------------------------------------


def test_us_4_1_user_scope_follows_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    switch = install_hermes(monkeypatch, root)
    resolved = {}
    for profile in ("a", "b", "default"):
        switch(profile)
        hermes_dir = sys.modules["plugins.plugin_storage"].plugin_data_dir("claimcoach")
        resolved[profile] = user_scope_dir()
        assert resolved[profile] == (hermes_dir / "user").resolve()
        assert active_profile() == profile
        # The worker resolves the same directory from the profile name.
        assert profile_user_scope_dir(profile, root) == resolved[profile]
    assert len(set(resolved.values())) == 3
    assert resolved["default"] == root / "plugin-data/claimcoach/user"


def test_us_4_1_active_profile_outside_hermes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profiles" / "biller-b"))
    assert active_profile() == "biller-b"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert active_profile() == "default"


def test_us_4_1_user_scopes_lists_initialized_profiles(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    service = make_service(tmp_path, corpus_server)
    for profile in ("default", "b", "a"):
        service.user_store(profile, create=True)
    (tmp_path / "profiles" / "not-a-scope").mkdir()
    (tmp_path / "profiles" / "bad name").mkdir()
    (tmp_path / "profiles" / "default").mkdir()  # a profile cannot be called "default"
    (tmp_path / "profiles" / "stray-file").write_text("x")
    assert list(user_scopes(tmp_path)) == ["default", "a", "b"]
    service.close()
    assert user_scopes(tmp_path / "empty") == {}


# --- Scenario: Invalid profile name -------------------------------------------------------------


@pytest.mark.parametrize("name", ["../x", "a/b", "..", "", "x" * 65, "sp ace"])
def test_us_4_1_invalid_profile_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(InvalidProfileError):
        profile_home(name, tmp_path)
    with pytest.raises(InvalidProfileError):
        profile_user_scope_dir(name, tmp_path)
    assert not (tmp_path / "profiles").exists()
    with pytest.raises(ValidationError):
        ReindexRequest(scope=CorpusScope.USER, profile=name)


async def test_us_4_1_invalid_profile_refused_by_routes(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    service = make_service(tmp_path, corpus_server)
    with corpus_client(service) as (_, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://w") as http:
            audit = await http.get("/corpus/audit", params={"profile": "../x"}, headers=AUTH)
            reindex = await http.post(
                "/corpus/reindex", json={"scope": "user", "profile": "a/b"}, headers=AUTH
            )
    for response in (audit, reindex):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"
        assert "../x" not in response.text
    assert not (tmp_path / "profiles").exists()


# --- Scenario: Each scope has its own database and vector index ---------------------------------


def test_us_4_1_each_scope_own_db_and_index(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    service = make_service(tmp_path, corpus_server)
    global_store, user_store = service.global_store(), service.user_store("default", create=True)
    put_global(global_store, global_doc())
    add_case_document(user_store, "case-1", "Claim for office visit denied CO-197.")
    files = set()
    for store in (global_store, user_store):
        for name in (DATABASE, INDEX):
            path = store.directory / name
            files.add(path)
            assert path.stat().st_mode & 0o777 == 0o600
            with sqlite3.connect(path) as probe:
                assert probe.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        info = store.index_info()
        assert info.embedding_model_id == MODEL_ID
        assert "Qwen3-Embedding-8B" in info.embedding_model_id
        assert not info.needs_reindex
        assert info.dimension == EMBED_DIM
        assert info.vectors == 1
    assert len(files) == 4
    assert global_store.directory == tmp_path / "plugin-data/claimcoach/global"
    assert user_store.directory == tmp_path / "plugin-data/claimcoach/user"
    # The scopes never mix: each index holds only its own chunk.
    assert [d.doc_id for d in global_store.documents()] == ["rule_card:aetna"]
    assert [d.case_id for d in user_store.documents("case-1")] == ["case-1"]
    status = service.status()
    assert status.global_scope.encrypted is False
    assert [s.profile for s in status.user_scopes] == ["default"]
    assert status.user_scopes[0].encrypted is True
    assert (status.user_scopes[0].cases, status.user_scopes[0].documents) == (1, 1)
    service.close()
    service.close()  # idempotent


# --- Scenario: A model change forces reindex ----------------------------------------------------


async def test_us_4_1_model_change_forces_reindex(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    old = make_service(tmp_path, corpus_server, model_id="Old-Embedding")
    put_global(old.global_store(), global_doc())
    old.close()

    service = make_service(tmp_path, corpus_server)
    store = service.global_store()
    info = store.index_info()
    assert (info.embedding_model_id, info.configured_model_id) == ("Old-Embedding", MODEL_ID)
    assert info.needs_reindex
    query = vectors_for(["timely"])[0]
    with pytest.raises(IndexStaleError):
        store.search(query, 3)
    with pytest.raises(IndexStaleError):
        put_global(store, global_doc("cigna"))

    with corpus_client(service) as (client, _):
        status = await client.corpus_status()
        assert status.global_scope.index is not None
        assert status.global_scope.index.needs_reindex
        result = await client.reindex_corpus(ReindexRequest(scope=CorpusScope.GLOBAL))
    assert (result.chunks, result.embedding_model_id) == (1, MODEL_ID)
    assert not store.index_info().needs_reindex
    assert [chunk_id for chunk_id, _ in store.search(query, 3)] == ["rule_card:aetna#0"]


async def test_us_4_1_reindex_route_user_scope_and_stale_envelope(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    old = make_service(tmp_path, corpus_server, model_id="Old-Embedding")
    keys = old._keys
    old.global_store()
    add_case_document(old.user_store("a", create=True), "c1", "Denied for timely filing.")
    old.close()
    service = make_service(tmp_path, corpus_server, keys=keys)
    with corpus_client(service) as (_, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://w") as http:
            stale = await http.post("/corpus/import", json=bundle_json(), headers=AUTH)
            done = await http.post(
                "/corpus/reindex", json={"scope": "user", "profile": "a"}, headers=AUTH
            )
            empty = await http.post("/corpus/reindex", json={"scope": "global"}, headers=AUTH)
    assert stale.status_code == 409
    assert stale.json() == {
        "ok": False,
        "error": {"code": "index_stale", "message": ERROR_MESSAGES["index_stale"]},
    }
    assert done.json()["chunks"] == 1
    assert empty.json()["chunks"] == 0
    assert not service.user_store("a", create=True).index_info().needs_reindex


def bundle_json() -> dict[str, object]:
    return {
        "items": [
            {
                "kind": "code",
                "code_set": "CARC",
                "code": "197",
                "title": "Precertification absent",
                "body": "Payment denied: precertification was not obtained.",
                "source": "X12 CARC list",
                "verified_on": "2026-07-01",
            }
        ]
    }


def test_us_4_1_dimension_change_refused(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path, CorpusScope.GLOBAL, embedding_model_id=MODEL_ID)
    put_global(store, global_doc())
    short = np.ones((1, 8), dtype=np.float32)
    with pytest.raises(IndexStaleError):
        store.put_document(global_doc("other"), ["x"], short)
    with pytest.raises(IndexStaleError):
        store.search(short[0], 1)
    store.close()


# --- Store guards -------------------------------------------------------------------------------


def test_us_4_1_store_guards(tmp_path: Path) -> None:
    cipher = Cipher(b"k" * 32)
    with pytest.raises(CorpusError):
        CorpusStore(tmp_path / "u", CorpusScope.USER, embedding_model_id=MODEL_ID)
    with pytest.raises(CorpusError):
        CorpusStore(tmp_path / "g", CorpusScope.GLOBAL, embedding_model_id=MODEL_ID, cipher=cipher)
    CorpusStore(tmp_path / "g", CorpusScope.GLOBAL, embedding_model_id=MODEL_ID).close()
    with pytest.raises(CorpusError):  # these files belong to the global scope
        CorpusStore(
            tmp_path / "g",
            CorpusScope.USER,
            embedding_model_id=MODEL_ID,
            cipher=cipher,
            profile="default",
        )
    (tmp_path / "file").write_text("x")
    with pytest.raises(CorpusError):
        CorpusStore(tmp_path / "file", CorpusScope.GLOBAL, embedding_model_id=MODEL_ID)
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / DATABASE).write_bytes(b"not a database" * 100)
    with pytest.raises(CorpusError):
        CorpusStore(tmp_path / "bad", CorpusScope.GLOBAL, embedding_model_id=MODEL_ID)

    with CorpusStore(tmp_path / "g", CorpusScope.GLOBAL, embedding_model_id=MODEL_ID) as store:
        with pytest.raises(CorpusError):
            store.documents("case-1")
        with pytest.raises(CorpusError):
            store.search(vectors_for(["x"])[0], 1, case_id="case-1")
        with pytest.raises(CorpusError):
            store.create_case("case-1")
        with pytest.raises(CorpusError):
            store.open_case("case-1")
        with pytest.raises(CorpusError):  # no chunks
            store.put_document(global_doc(), [], vectors_for([]))
        with pytest.raises(CorpusError):  # counts differ
            store.put_document(global_doc(), ["a", "b"], vectors_for(["a"]))
        user_doc = Document(
            doc_id="d", scope=CorpusScope.USER, case_id="c", kind="source", title="t", text="x"
        )
        with pytest.raises(CorpusError):
            store.put_document(user_doc, ["x"], vectors_for(["x"]))
        with pytest.raises(CorpusError):
            store.replace_index(["missing#0"], vectors_for(["x"]))
        assert store.search(vectors_for(["x"])[0], 3) == []
        assert store.chunks([]) == []

    with CorpusStore(
        tmp_path / "u", CorpusScope.USER, embedding_model_id=MODEL_ID, cipher=cipher, profile="p"
    ) as user:
        with pytest.raises(CorpusError):
            user.documents()
        with pytest.raises(CorpusError):
            user.chunks(["x"])
        with pytest.raises(CaseNotFoundError):
            user.open_case("nope")
        with pytest.raises(CaseNotFoundError):
            user.close_case("nope")
        with pytest.raises(CaseNotFoundError):
            add_case_document(user, "nope", "text", create=False)
        user.create_case("c")
        with pytest.raises(CorpusError):
            user.create_case("c")
        assert user.outcome("c") is None


def test_us_4_1_document_scope_consistency() -> None:
    with pytest.raises(ValidationError):
        Document(doc_id="d", scope=CorpusScope.USER, kind="source", title="t", text="x")
    with pytest.raises(ValidationError):
        Document(
            doc_id="d", scope=CorpusScope.USER, case_id="c", kind="rule_card", title="t", text="x"
        )
    with pytest.raises(ValidationError):
        Document(
            doc_id="d", scope=CorpusScope.GLOBAL, case_id="c", kind="code", title="t", text="x"
        )
    with pytest.raises(ValidationError):
        Document(doc_id="d", scope=CorpusScope.GLOBAL, kind="source", title="t", text="x")
    from datetime import datetime  # noqa: PLC0415

    with pytest.raises(ValidationError, match="timezone"):
        Document(
            doc_id="d",
            scope=CorpusScope.GLOBAL,
            kind="code",
            title="t",
            text="x",
            created_at=datetime(2026, 1, 1),
        )


def test_us_4_1_orphan_vectors_removed_on_open(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path, CorpusScope.GLOBAL, embedding_model_id=MODEL_ID)
    put_global(store, global_doc())
    store.close()
    with sqlite3.connect(tmp_path / INDEX) as raw:
        raw.execute("INSERT INTO vectors VALUES ('ghost#0', NULL, x'00000000')")
    with CorpusStore(tmp_path, CorpusScope.GLOBAL, embedding_model_id=MODEL_ID) as reopened:
        assert reopened.index_info().vectors == 1


def test_us_4_1_replacing_a_document_replaces_its_chunks(tmp_path: Path) -> None:
    with CorpusStore(tmp_path, CorpusScope.GLOBAL, embedding_model_id=MODEL_ID) as store:
        put_global(store, global_doc(text="one\n\n" + "two " * 400))
        assert store.status().chunks == 3
        put_global(store, global_doc(text="short"))
        status = store.status()
        assert (status.documents, status.chunks, store.index_info().vectors) == (1, 1, 1)
        assert store.chunks(["rule_card:aetna#0", "rule_card:aetna#0", "x"])[0].text == "short"


# --- Chunking -----------------------------------------------------------------------------------


def test_us_4_1_split_text() -> None:
    assert split_text("short") == ["short"]
    assert split_text("  \n\n ") == []
    paragraphs = split_text("a" * 50 + "\n\n" + "b" * 50 + "\n\n" + "c" * 30, size=110)
    assert paragraphs == ["a" * 50 + "\n\n" + "b" * 50, "c" * 30]
    lines = split_text("x" * 60 + "\n" + "y" * 60, size=80)
    assert lines == ["x" * 60, "y" * 60]
    words = split_text("w" * 30 + " " + "v" * 30 + " " + "u" * 30, size=40)
    assert words == ["w" * 30, "v" * 30, "u" * 30]
    assert split_text("z" * 25, size=10) == ["z" * 10, "z" * 10, "z" * 5]
    big = split_text("p" * 15 + "\n\n" + "q" * 25, size=20)
    assert big == ["p" * 15, "q" * 20, "q" * 5]


# --- Embedder ----------------------------------------------------------------------------------


async def test_us_4_1_embedder_batches(corpus_server: FakeModelServer) -> None:
    corpus_server.embedding_requests.clear()
    embedder = Embedder(static_models(corpus_server.base_url))
    assert embedder.__class__ is Embedder
    empty = await embedder.embed_documents([])
    assert empty.shape == (0, 0)
    vectors = await embedder.embed_documents([f"text {i}" for i in range(20)])
    assert vectors.shape == (20, EMBED_DIM)
    assert vectors.dtype == np.float32
    assert [len(r.input) for r in corpus_server.embedding_requests] == [16, 4]


def mock(body: object, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(status, json=body))


@pytest.mark.parametrize(
    "transport",
    [
        mock({"error": "down"}, 503),
        mock({"data": "nope"}),
        mock({"data": [{"index": 1, "embedding": [1.0]}]}),
        mock({"data": [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [1.0, 2.0]}]}),
    ],
    ids=["http-error", "bad-body", "wrong-index", "ragged"],
)
async def test_us_4_1_embedder_failures(transport: httpx.MockTransport) -> None:
    embedder = Embedder(static_models("http://127.0.0.1:9/v1"), transport=transport)
    with pytest.raises(ModelUnavailableError):
        await embedder.embed_documents(["a", "b"])


# --- Backup and restore (runbook) ---------------------------------------------------------------


def test_us_4_1_backup_restore_round_trip(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    root = tmp_path / "hermes"
    service = make_service(root, corpus_server)
    keys = service._keys
    put_global(service.global_store(), global_doc())
    add_case_document(service.user_store("a", create=True), "c1", "Appeal letter for the knee MRI.")
    folder = backup(root, tmp_path / "backups")
    assert folder.stat().st_mode & 0o777 == 0o700
    assert sorted(p.name for p in folder.iterdir()) == ["global", "user-a"]
    assert all(
        (folder / scope / name).stat().st_mode & 0o777 == 0o600
        for scope in ("global", "user-a")
        for name in (DATABASE, INDEX)
    )
    put_global(service.global_store(), global_doc("cigna", "Cigna appeals within 60 days."))
    service.close()

    assert restore(root, folder) == ["global", "user-a"]
    restored = make_service(root, corpus_server, keys=keys)
    assert [d.doc_id for d in restored.global_store().documents()] == ["rule_card:aetna"]
    assert (
        restored.user_store("a", create=True).documents("c1")[0].text
        == "Appeal letter for the knee MRI."
    )
    restored.close()


def test_us_4_1_backup_restore_refusals(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="no corpus scope"):
        backup(tmp_path / "hermes", tmp_path / "out")
    with pytest.raises(BackupError, match="no scope backup"):
        restore(tmp_path / "hermes", tmp_path / "missing")
    (tmp_path / "partial" / "global").mkdir(parents=True)
    (tmp_path / "partial" / "global" / DATABASE).write_text("")
    (tmp_path / "partial" / "other").mkdir()
    with pytest.raises(BackupError):
        restore(tmp_path / "hermes", tmp_path / "partial")


def test_us_4_1_makefile_corpus_targets() -> None:
    listing = subprocess.run(
        ["make", "-s", "help"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    for target in (
        "corpus-status",
        "corpus-reindex",
        "corpus-backup",
        "corpus-restore",
        "corpus-import",
        "corpus-list",
        "corpus-purge",
        "corpus-audit",
    ):
        assert target in listing
    dry = subprocess.run(
        ["make", "-n", "corpus-reindex", "SCOPE=global"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "HERMES_HOME": "/nonexistent"},
    ).stdout
    assert "claimcoach.cli corpus reindex --scope global" in dry
    bad = subprocess.run(
        ["make", "-n", "corpus-reindex", "SCOPE=nope"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode != 0
    assert paths.GLOBAL_DIR == "global"


# --- Review regressions -------------------------------------------------------------------------


def test_us_4_1_reads_never_create_a_profile(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    from claimcoach.corpus.errors import ProfileNotFoundError  # noqa: PLC0415

    service = make_service(tmp_path, corpus_server)
    for read in (
        lambda: service.user_store("typo"),
        lambda: service.audit("typo"),
    ):
        with pytest.raises(ProfileNotFoundError):
            read()
    assert not (tmp_path / "profiles").exists()
    assert service._keys.keys == {}  # type: ignore[attr-defined]  # no key was created


def test_us_4_1_status_reports_a_profile_that_does_not_open(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    from claimcoach.corpus.crypto import InMemoryKeyProvider  # noqa: PLC0415

    setup = make_service(tmp_path, corpus_server)
    keys = setup._keys
    setup.user_store("a", create=True)
    setup.user_store("b", create=True)
    setup.close()
    partial = InMemoryKeyProvider()
    partial.keys = {"user-store:a": keys.keys["user-store:a"]}  # type: ignore[attr-defined]
    service = make_service(tmp_path, corpus_server, keys=partial)
    status = service.status()
    by_profile = {s.profile: s for s in status.user_scopes}
    assert by_profile["a"].available is True
    assert by_profile["b"].available is False
    assert by_profile["b"].index is None
    assert "b" not in {k.removeprefix("user-store:") for k in partial.keys} - {"a"}


def test_us_4_1_missing_vectors_force_reindex(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    service = make_service(tmp_path, corpus_server)
    store = service.global_store()
    put_global(store, global_doc())
    with sqlite3.connect(store.directory / INDEX) as raw:
        raw.execute("DELETE FROM vectors")
    info = store.index_info()
    assert (info.missing_vectors, info.needs_reindex) == (1, True)


async def test_us_4_1_reindex_writes_new_vectors(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    old = make_service(tmp_path, corpus_server, model_id="Old-Embedding")
    put_global(old.global_store(), global_doc())
    old.close()
    chunk_text = global_doc().text
    new_vector = [0.0] * EMBED_DIM
    new_vector[7] = 1.0
    corpus_server.embed_overrides[chunk_text] = new_vector
    try:
        service = make_service(tmp_path, corpus_server)
        await service.reindex(ReindexRequest(scope=CorpusScope.GLOBAL))
        hits = service.global_store().search(np.asarray(new_vector, dtype=np.float32), 1)
    finally:
        corpus_server.embed_overrides.clear()
    assert hits[0][0] == "rule_card:aetna#0"
    assert hits[0][1] == pytest.approx(1.0)  # the stored vector is the new model's


def test_us_4_1_backup_is_one_snapshot_and_refusal_creates_nothing(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    root = tmp_path / "hermes"
    with pytest.raises(BackupError):
        backup(root, tmp_path / "out")
    assert not root.exists()  # resolving the scopes created no folder
    service = make_service(root, corpus_server)
    put_global(service.global_store(), global_doc())
    (tmp_path / "not-a-dir").write_text("x")
    with pytest.raises(BackupError, match="nothing was kept"):
        backup(root, tmp_path / "not-a-dir")
    folder = backup(root, tmp_path / "out")
    with sqlite3.connect(folder / "global" / DATABASE) as db:
        db.execute("ATTACH DATABASE ? AS idx", (str(folder / "global" / INDEX),))
        missing = db.execute(
            "SELECT count(*) FROM chunks WHERE chunk_id NOT IN (SELECT chunk_id FROM idx.vectors)"
        ).fetchone()[0]
    assert missing == 0
    service.close()


def test_us_4_1_restore_validates_first_and_fails_safe(
    tmp_path: Path, corpus_server: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil  # noqa: PLC0415

    root = tmp_path / "hermes"
    service = make_service(root, corpus_server)
    put_global(service.global_store(), global_doc())
    folder = backup(root, tmp_path / "out")
    service.close()
    bad = tmp_path / "bad"
    shutil.copytree(folder, bad)
    shutil.copytree(folder / "global", bad / "user-Not_Hermes")
    before = (root / "plugin-data/claimcoach/global" / DATABASE).read_bytes()
    with pytest.raises(BackupError, match="invalid profile"):
        restore(root, bad)
    calls = {"n": 0}
    real_copy = shutil.copy2

    def flaky_copy(src: Path, dst: Path) -> object:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_copy(src, dst)

    monkeypatch.setattr(shutil, "copy2", flaky_copy)
    with pytest.raises(BackupError, match="left as it was"):
        restore(root, folder)
    live = root / "plugin-data/claimcoach/global"
    assert (live / DATABASE).read_bytes() == before
    assert not list(live.glob("*.restoring"))


def test_us_4_1_worker_main_mounts_the_corpus(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import uvicorn  # noqa: PLC0415

    from claimcoach.worker import __main__ as worker_main  # noqa: PLC0415

    apps: list[object] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **_kw: apps.append(app))
    data = tmp_path / "hermes" / "plugin-data" / "claimcoach"
    assert worker_main.main(["--data-dir", str(data), "--port", "18201"]) == 0
    service = apps[0].state.corpus  # type: ignore[attr-defined]
    assert service.root == (tmp_path / "hermes").resolve()
    assert "Qwen3-Embedding-8B" in service.embedding_model_id
    assert worker_main.main(["--data-dir", str(tmp_path / "elsewhere"), "--port", "18201"]) == 0
    assert not hasattr(apps[1].state, "corpus")  # type: ignore[attr-defined]


async def test_us_4_1_lifespan_survives_a_dead_task(caplog: pytest.LogCaptureFixture) -> None:
    from claimcoach.worker.app import _lifespan  # noqa: PLC0415

    stopped: list[str] = []

    async def dies() -> None:
        raise RuntimeError("boom with PHI Jane Doe")

    async def runs() -> None:
        await asyncio.sleep(3600)

    async def stop() -> None:
        stopped.append("stopped")

    lifespan = _lifespan([dies, runs], [stop])
    with caplog.at_level(logging.ERROR):
        async with lifespan(None):  # type: ignore[arg-type]
            await asyncio.sleep(0.01)
    assert stopped == ["stopped"]
    assert "background task ended: RuntimeError" in caplog.text
    assert "Jane" not in caplog.text
