"""US-4.2 User Scope Encrypted at Rest.

Scenarios: user store files are not plaintext; the key lives in the Keychain. Also: a wrong key
fails closed, Keychain failures fail closed, and the cipher binds each value to its row. The real
Keychain path runs against a throwaway keychain under ``tmp_path`` that is never added to the
user's search list. Rules: BR-6, BR-14.
"""

from __future__ import annotations

import os
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from claimcoach.api.models import ERROR_MESSAGES
from claimcoach.corpus.crypto import (
    KEY_BYTES,
    KEY_SERVICE,
    Cipher,
    InMemoryKeyProvider,
    KeychainKeyProvider,
    key_account,
)
from claimcoach.corpus.errors import CorpusKeyError
from tests.fakes.corpus import (
    TOKEN,
    add_case_document,
    corpus_client,
    make_service,
    vectors_for,
)
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, seeded_strings

SECURITY = Path("/usr/bin/security")
pytestmark = pytest.mark.skipif(not SECURITY.exists(), reason="macOS Keychain tools not present")


@pytest.fixture
def keychain(tmp_path: Path) -> Iterator[Path]:
    """A throwaway, unlocked keychain file; deleted afterwards."""
    path = tmp_path / "keychains" / "claimcoach-test.keychain-db"
    path.parent.mkdir()
    password = "claimcoach-test"
    subprocess.run([SECURITY, "create-keychain", "-p", password, path], check=True)
    try:
        subprocess.run([SECURITY, "unlock-keychain", "-p", password, path], check=True)
        yield path
    finally:
        subprocess.run([SECURITY, "delete-keychain", path], check=False)


def scope_bytes(directory: Path) -> bytes:
    """Every byte of every file in a scope directory (database, WAL, SHM, index)."""
    return b"".join(p.read_bytes() for p in sorted(directory.rglob("*")) if p.is_file())


def all_bytes(root: Path) -> bytes:
    return b"".join(
        p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and "keychains" not in p.parts
    )


# --- Scenario: User store files are not plaintext -----------------------------------------------


def test_us_4_2_user_store_not_plaintext(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    document = PHI_DOCUMENTS[0]
    seeded = list(seeded_strings(document))
    assert seeded
    service = make_service(tmp_path, corpus_server)
    store = service.user_store("default", create=True)
    patient = document["phi"]["name"][0]
    add_case_document(store, "case-phi", document["text"], title=f"Denial for {patient}")
    # The encrypted vector index still answers for its case.
    assert store.search(vectors_for(["denied"])[0], 1, case_id="case-phi")

    for raw in (scope_bytes(store.directory), all_bytes(tmp_path)):
        lowered = raw.lower()
        found = [value for value in seeded if value.lower().encode() in lowered]
        assert found == []
    # Not vacuous: the content decrypts through the store.
    stored = store.documents("case-phi")[0]
    assert stored.text == document["text"]
    assert stored.title == f"Denial for {patient}"
    service.close()
    assert [v for v in seeded if v.lower().encode() in all_bytes(tmp_path).lower()] == []


# --- Scenario: Wrong key fails closed -----------------------------------------------------------


async def test_us_4_2_wrong_key_fails_closed(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    first = make_service(tmp_path, corpus_server)
    add_case_document(
        first.user_store("default", create=True), "c1", "Member ID W123456789 denied."
    )
    first.close()

    other = make_service(tmp_path, corpus_server, keys=InMemoryKeyProvider())
    with pytest.raises(CorpusKeyError):
        other.user_store("default", create=True)
    with corpus_client(other) as (_, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://w") as http:
            response = await http.get("/corpus/audit", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503
    assert response.json() == {
        "ok": False,
        "error": {"code": "corpus_unavailable", "message": ERROR_MESSAGES["corpus_unavailable"]},
    }


def test_us_4_2_cipher_binds_value_to_row() -> None:
    cipher = Cipher(os.urandom(KEY_BYTES))
    blob = cipher.encrypt(b"Jane Doe", "chunks:a#0")
    assert b"Jane" not in blob
    assert cipher.decrypt(blob, "chunks:a#0") == b"Jane Doe"
    assert cipher.encrypt(b"Jane Doe", "chunks:a#0") != blob  # fresh nonce per value
    with pytest.raises(CorpusKeyError):
        cipher.decrypt(blob, "chunks:b#0")
    with pytest.raises(CorpusKeyError):
        cipher.decrypt(blob[:-1] + bytes([blob[-1] ^ 1]), "chunks:a#0")
    with pytest.raises(CorpusKeyError):
        Cipher(b"short")


def test_us_4_2_in_memory_provider_is_stable() -> None:
    keys = InMemoryKeyProvider()
    assert keys.key_for("a", create=True) == keys.key_for("a", create=True)
    assert keys.key_for("a", create=True) != keys.key_for("b", create=True)
    assert len(keys.key_for("a", create=True)) == KEY_BYTES


# --- Scenario: The key lives in the Keychain ----------------------------------------------------


def test_us_4_2_key_in_keychain(
    tmp_path: Path, keychain: Path, corpus_server: FakeModelServer
) -> None:
    root = tmp_path / "hermes"
    provider = KeychainKeyProvider(keychain)
    service = make_service(root, corpus_server, keys=provider)
    add_case_document(service.user_store("biller-a", create=True), "c1", "Patient DOB 04/12/1961.")
    service.close()

    found = subprocess.run(
        [
            SECURITY,
            "find-generic-password",
            "-s",
            KEY_SERVICE,
            "-a",
            "user-store:biller-a",
            "-w",
            keychain,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    key = bytes.fromhex(found.stdout.strip())
    assert len(key) == KEY_BYTES
    assert key_account("biller-a") == "user-store:biller-a"
    # Persisted, not regenerated: the store reopens with the Keychain item.
    assert provider.key_for("user-store:biller-a", create=True) == key
    reopened = make_service(root, corpus_server, keys=provider)
    assert (
        reopened.user_store("biller-a", create=True).documents("c1")[0].text
        == "Patient DOB 04/12/1961."
    )
    reopened.close()
    # The key is not in any file of the plugin data dir, in raw or hex form.
    data = all_bytes(root)
    assert key not in data
    assert key.hex().encode() not in data
    assert key.hex().upper().encode() not in data


# --- Scenario: Keychain failure -----------------------------------------------------------------


def fake_security(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "security"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.mark.parametrize(
    "body",
    [
        "exit 51",  # e.g. the keychain is locked or access was denied
        'echo "not hex"',
        "echo abcd",  # hex but not 32 bytes
        'case "$1" in -i) cat >/dev/null;; *) exit 44;; esac',  # the add silently fails
        "printf '\\377\\376'",  # not ASCII
    ],
    ids=["denied", "not-hex", "short-key", "add-lost", "binary"],
)
def test_us_4_2_keychain_failure_fails_closed(tmp_path: Path, body: str) -> None:
    provider = KeychainKeyProvider(security=fake_security(tmp_path, body))
    with pytest.raises(CorpusKeyError):
        provider.key_for("user-store:default", create=True)


def test_us_4_2_keychain_unreachable_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CorpusKeyError):
        KeychainKeyProvider(security=tmp_path / "missing").key_for(
            "user-store:default", create=True
        )
    slow = KeychainKeyProvider(security=fake_security(tmp_path, "sleep 5"), timeout=0.2)
    with pytest.raises(CorpusKeyError):
        slow.key_for("user-store:default", create=True)


def test_us_4_2_key_never_in_argv(tmp_path: Path) -> None:
    """The add passes the key on stdin to ``security -i``; argv never carries it."""
    log = tmp_path / "argv.log"
    stdin = tmp_path / "stdin.log"
    key_file = tmp_path / "key"
    script = fake_security(
        tmp_path,
        f'echo "$@" >> {log}\n'
        f'if [ "$1" = "-i" ]; then cat > {stdin}; '
        f"sed -E 's/.* -w ([0-9a-f]+).*/\\1/' {stdin} > {key_file}; exit 0; fi\n"
        f"if [ -s {key_file} ]; then cat {key_file}; else exit 44; fi",
    )
    key = KeychainKeyProvider(security=script).key_for("user-store:default", create=True)
    assert len(key) == KEY_BYTES
    assert key.hex() not in log.read_text()
    assert key.hex() in stdin.read_text()
    assert f'-s "{KEY_SERVICE}" -a "user-store:default"' in stdin.read_text()


# --- Review regressions -------------------------------------------------------------------------


def test_us_4_2_existing_store_never_gets_a_new_key(
    tmp_path: Path, keychain: Path, corpus_server: FakeModelServer
) -> None:
    """A restored store whose Keychain item is missing fails closed and writes no key."""
    first = make_service(tmp_path, corpus_server)
    add_case_document(first.user_store("default", create=True), "c1", "MRN 0042 denied.")
    first.close()
    empty = KeychainKeyProvider(keychain)
    service = make_service(tmp_path, corpus_server, keys=empty)
    with pytest.raises(CorpusKeyError):
        service.user_store("default")
    assert service.purge_all().skipped == ["default"]
    probe = subprocess.run(
        [
            SECURITY,
            "find-generic-password",
            "-s",
            KEY_SERVICE,
            "-a",
            "user-store:default",
            keychain,
        ],
        capture_output=True,
        check=False,
    )
    assert probe.returncode == 44  # still no item: importing the real key stays possible
    with pytest.raises(CorpusKeyError):
        InMemoryKeyProvider().key_for("user-store:default", create=False)


def test_us_4_2_key_export_and_import_round_trip(
    tmp_path: Path,
    keychain: Path,
    corpus_server: FakeModelServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from claimcoach import cli  # noqa: PLC0415

    root = tmp_path / "hermes"
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setattr(cli, "keychain", lambda: KeychainKeyProvider(keychain))
    service = make_service(root, corpus_server, keys=KeychainKeyProvider(keychain))
    add_case_document(service.user_store("default", create=True), "c1", "DOB 01/02/1960.")
    service.close()
    key_file = tmp_path / "default.key"
    out: list[str] = []

    def run(*argv: str) -> int:
        return cli.run(cli.build_parser().parse_args(argv), out=out.append)

    assert run("corpus", "key-export", "--to", str(key_file)) == 0
    assert key_file.stat().st_mode & 0o777 == 0o600
    exported = bytes.fromhex(key_file.read_text().strip())
    assert run("corpus", "key-export", "--to", str(key_file)) == 2  # never overwrites
    assert out[-1] == "error: the file cannot be written"

    # A new Mac: an empty keychain, then the key is imported.
    subprocess.run(
        [
            SECURITY,
            "delete-generic-password",
            "-s",
            KEY_SERVICE,
            "-a",
            "user-store:default",
            keychain,
        ],
        capture_output=True,
        check=True,
    )
    assert run("corpus", "key-export", "--to", str(tmp_path / "none.key")) == 1
    assert out[-1] == "error: corpus_unavailable"
    assert run("corpus", "key-import", "--from", str(key_file)) == 2
    assert out[-1] == "error: key-import replaces the Keychain item; re-run with --confirm"
    assert run("corpus", "key-import", "--from", str(key_file), "--confirm") == 0
    assert KeychainKeyProvider(keychain).key_for("user-store:default", create=False) == exported
    reopened = make_service(root, corpus_server, keys=KeychainKeyProvider(keychain))
    assert reopened.user_store("default").documents("c1")[0].text == "DOB 01/02/1960."
    reopened.close()
    (tmp_path / "bad.key").write_text("not hex")
    assert run("corpus", "key-import", "--from", str(tmp_path / "bad.key"), "--confirm") == 2
    assert out[-1] == "error: the key file cannot be read"


def test_us_4_2_store_key_refusals(tmp_path: Path) -> None:
    provider = KeychainKeyProvider(security=fake_security(tmp_path, "exit 44"))
    with pytest.raises(CorpusKeyError):
        provider.store_key("user-store:default", b"short", replace=True)
    with pytest.raises(CorpusKeyError):  # security -i "succeeded" but nothing was stored
        provider.store_key("user-store:default", b"k" * KEY_BYTES, replace=True)
    other = b"o" * KEY_BYTES
    keeps_other = KeychainKeyProvider(security=fake_security(tmp_path, f"echo {other.hex()}"))
    with pytest.raises(CorpusKeyError):  # the Keychain kept a different key
        keeps_other.store_key("user-store:default", b"k" * KEY_BYTES, replace=True)
    assert keeps_other.store_key("user-store:default", b"k" * KEY_BYTES, replace=False) == other


def test_us_4_2_ciphertext_is_bound_to_its_case(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    import sqlite3  # noqa: PLC0415

    from claimcoach.corpus.paths import DATABASE  # noqa: PLC0415

    service = make_service(tmp_path, corpus_server)
    store = service.user_store("default", create=True)
    add_case_document(store, "case-a", "Patient Jane Doe, MRN 0042.")
    store.create_case("case-b")
    with sqlite3.connect(store.directory / DATABASE) as raw:
        raw.execute("UPDATE chunks SET case_id = 'case-b'")
    chunk_id = f"case-a-src-{len('Patient Jane Doe, MRN 0042.')}#0"
    with pytest.raises(CorpusKeyError):  # moved rows do not decrypt as the other case
        store.chunks([chunk_id], case_id="case-b")


def test_us_4_2_tampered_values_fail_closed(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    import sqlite3  # noqa: PLC0415

    from claimcoach.corpus.paths import DATABASE  # noqa: PLC0415

    cipher = Cipher(os.urandom(KEY_BYTES))
    with pytest.raises(CorpusKeyError):
        cipher.decrypt(b"\x00\x01", "chunks::x")  # shorter than a nonce
    first = make_service(tmp_path, corpus_server)
    keys = first._keys
    first.user_store("default", create=True)
    first.close()
    with sqlite3.connect(tmp_path / "plugin-data/claimcoach/user" / DATABASE) as raw:
        raw.execute("UPDATE meta SET value = 'zz' WHERE key = 'key_check'")
    with pytest.raises(CorpusKeyError):
        make_service(tmp_path, corpus_server, keys=keys).user_store("default")


def test_us_4_2_user_document_ids_are_opaque() -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from claimcoach.corpus.types import CorpusScope, Document  # noqa: PLC0415

    with pytest.raises(ValidationError, match="opaque"):
        Document(
            doc_id="Smith_John_1961-04-12.pdf",
            scope=CorpusScope.USER,
            case_id="c1",
            kind="source",
            title="t",
            text="x",
        )


def test_us_4_2_cli_uses_the_login_keychain_by_default() -> None:
    from claimcoach import cli  # noqa: PLC0415

    provider = cli.keychain()  # constructing it runs nothing
    assert isinstance(provider, KeychainKeyProvider)
    assert provider._keychain is None  # the user's default search list
