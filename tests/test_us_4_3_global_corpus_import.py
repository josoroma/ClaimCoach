"""US-4.3 Global Corpus Import with Provenance.

Scenario: imported rule cards keep provenance. Also: stale cards are flagged, missing provenance
fails the whole import, re-import replaces, the bundle parser's refusals, the
``hermes claimcoach corpus`` registration, and every CLI subcommand. The CLI runs against the
worker app over an ASGI transport. Rules: BR-1, ES-1, ES-8, PRD §11.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach import cli
from claimcoach.api.client import WorkerClient
from claimcoach.corpus.bundle import (
    MAX_BUNDLE_BYTES,
    BundleError,
    CorpusBundle,
    is_stale,
    parse_bundle,
)
from claimcoach.corpus.embed import Embedder
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.importer import import_bundle
from claimcoach.corpus.service import CorpusService
from claimcoach.models.manager import ModelUnavailableError
from claimcoach.paths import app_data_dir
from claimcoach.worker.app import create_app
from claimcoach.worker.config import WorkerConfig, WorkerHandle
from claimcoach.worker.token import issue_token
from tests.conftest import HERMES_ROOT, REPO_ROOT, free_port_in_range
from tests.fakes.corpus import TOKEN, add_case_document, corpus_client, make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.live_app import LiveApp
from tests.fakes.phi import static_models
from tests.fakes.registrar import FakeRegistrar
from tests.test_us_1_1_plugin_package import load_agent_half, probe_hermes

TODAY = date.today()
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def rule_card(verified_on: date = TODAY - timedelta(days=10), **extra: Any) -> dict[str, Any]:
    return {
        "kind": "rule_card",
        "payer": "Aetna",
        "topic": "timely_filing",
        "title": "Aetna timely filing limit",
        "body": "Corrected claims must be filed within 180 days of the original determination.",
        "source": "Aetna provider manual 2026, section 7.2",
        "verified_on": verified_on.isoformat(),
        **extra,
    }


def other_items() -> list[dict[str, Any]]:
    return [
        {
            "kind": "code",
            "code_set": "CARC",
            "code": "197",
            "title": "Precertification absent",
            "body": "Precertification/authorization/notification/pre-treatment absent.",
            "source": "X12 CARC list, 2026-07",
            "verified_on": (TODAY - timedelta(days=200)).isoformat(),
        },
        {
            "kind": "letter_template",
            "template_id": "medical-necessity-l1",
            "title": "Level 1 appeal: medical necessity",
            "body": "To the appeals department:\n\nWe request reconsideration of claim {claim}.",
            "source": "Practice template library v3",
            "verified_on": (TODAY - timedelta(days=30)).isoformat(),
        },
    ]


def write_bundle(path: Path, items: list[dict[str, Any]]) -> Path:
    path.write_text(yaml.safe_dump({"items": items}, sort_keys=False))
    return path


def args(*argv: str) -> argparse.Namespace:
    return cli.build_parser().parse_args(argv)


class Lines(list[str]):
    def __call__(self, line: str) -> None:
        self.append(line)


def run_cli(client: WorkerClient, *argv: str) -> tuple[int, Lines]:
    out = Lines()
    return cli.run(args(*argv), client=client, out=out), out


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> CorpusService:
    return make_service(tmp_path / "hermes", corpus_server)


# --- Scenario: Imported rule cards keep provenance ----------------------------------------------


def test_us_4_3_rule_card_keeps_provenance(tmp_path: Path, service: CorpusService) -> None:
    bundle = write_bundle(tmp_path / "rules.yaml", [rule_card(), *other_items()])
    with corpus_client(service) as (client, _):
        code, out = run_cli(client, "corpus", "import", str(bundle))
        assert (code, out) == (0, ["imported 1 code, 1 letter_template, 1 rule_card (3 chunks)"])
        code, view = run_cli(client, "corpus", "list")
    assert code == 0
    card = next(line for line in view if line.startswith("rule_card"))
    assert "Aetna/timely_filing" in card
    assert "Aetna provider manual 2026, section 7.2" in card
    assert (TODAY - timedelta(days=10)).isoformat() in card
    assert "STALE" not in card
    stored = service.global_store().documents()
    assert {d.doc_id for d in stored} == {
        "rule_card:Aetna/timely_filing",
        "code:CARC/197",
        "letter_template:medical-necessity-l1",
    }
    item = next(i for i in service.view().items if i.kind == "rule_card")
    assert (item.source, item.verified_on) == (
        "Aetna provider manual 2026, section 7.2",
        TODAY - timedelta(days=10),
    )


# --- Scenario: Stale rule card flagged ----------------------------------------------------------


def test_us_4_3_stale_card_flagged(tmp_path: Path, service: CorpusService) -> None:
    bundle = write_bundle(tmp_path / "rules.yml", other_items())
    with corpus_client(service) as (client, _):
        assert run_cli(client, "corpus", "import", str(bundle))[0] == 0
        _, view = run_cli(client, "corpus", "list")
    code_line = next(line for line in view if line.startswith("code"))
    template_line = next(line for line in view if line.startswith("letter_template"))
    assert "STALE" in code_line  # verified 200 days ago
    assert "STALE" not in template_line
    assert is_stale(TODAY - timedelta(days=181), TODAY)
    assert not is_stale(TODAY - timedelta(days=180), TODAY)


# --- Scenario: Missing provenance rejected ------------------------------------------------------


def card_without_date() -> dict[str, Any]:
    card = rule_card()
    del card["verified_on"]
    return card


def test_us_4_3_missing_provenance_rejected(tmp_path: Path, service: CorpusService) -> None:
    bundle = write_bundle(tmp_path / "bad.yaml", [*other_items(), card_without_date()])
    with corpus_client(service) as (client, _):
        code, out = run_cli(client, "corpus", "import", str(bundle))
    assert code == 2
    assert out == ["error: invalid bundle at items.2.rule_card.verified_on: missing"]
    assert service.global_store().documents() == []


async def test_us_4_3_missing_provenance_rejected_by_worker(service: CorpusService) -> None:
    with corpus_client(service) as (_, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://w") as http:
            response = await http.post(
                "/corpus/import",
                json={"items": [*other_items(), card_without_date()]},
                headers=AUTH,
            )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "Aetna" not in response.text
    assert service.global_store().documents() == []


# --- Scenario: Re-import replaces ---------------------------------------------------------------


def test_us_4_3_reimport_replaces(tmp_path: Path, service: CorpusService) -> None:
    first = write_bundle(tmp_path / "v1.json", [rule_card(TODAY - timedelta(days=300))])
    second = tmp_path / "v2.json"
    second.write_text(json.dumps({"items": [rule_card(TODAY - timedelta(days=1))]}))
    with corpus_client(service) as (client, _):
        assert run_cli(client, "corpus", "import", str(first))[0] == 0
        assert run_cli(client, "corpus", "import", str(second))[0] == 0
    items = service.view().items
    assert len(items) == 1
    assert items[0].verified_on == TODAY - timedelta(days=1)
    assert not items[0].stale
    status = service.global_store().status()
    vectors = service.global_store().index_info().vectors
    assert (status.documents, status.chunks, vectors) == (1, 1, 1)


# --- Bundle parser ------------------------------------------------------------------------------


def test_us_4_3_bundle_refusals(tmp_path: Path) -> None:
    with pytest.raises(BundleError, match=r"\.yaml"):
        parse_bundle(tmp_path / "rules.csv")
    (tmp_path / "dir.yaml").mkdir()
    with pytest.raises(BundleError, match="cannot be read"):
        parse_bundle(tmp_path / "dir.yaml")
    with pytest.raises(BundleError, match="cannot be read"):
        parse_bundle(tmp_path / "missing.yaml")
    (tmp_path / "binary.yaml").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(BundleError, match="cannot be read"):
        parse_bundle(tmp_path / "binary.yaml")
    (tmp_path / "broken.yaml").write_text("items: [unclosed")
    with pytest.raises(BundleError, match="not valid YAML"):
        parse_bundle(tmp_path / "broken.yaml")
    big = tmp_path / "big.yaml"
    big.write_bytes(b"#" * (MAX_BUNDLE_BYTES + 1))
    with pytest.raises(BundleError, match="5 MiB"):
        parse_bundle(big)
    (tmp_path / "empty.yaml").write_text("")
    with pytest.raises(BundleError, match="invalid bundle at bundle: model_type"):
        parse_bundle(tmp_path / "empty.yaml")
    future = write_bundle(tmp_path / "f.yaml", [rule_card(TODAY + timedelta(days=2))])
    with pytest.raises(BundleError, match="verified_on: value_error"):
        parse_bundle(future)
    extra = write_bundle(tmp_path / "x.yaml", [rule_card(patient="Jane Doe")])
    with pytest.raises(BundleError, match="extra_forbidden") as caught:
        parse_bundle(extra)
    assert "Jane" not in str(caught.value)
    duplicate = write_bundle(tmp_path / "d.yaml", [rule_card(), rule_card()])
    with pytest.raises(BundleError, match="value_error"):
        parse_bundle(duplicate)


async def test_us_4_3_import_guards(service: CorpusService) -> None:
    bundle = CorpusBundle.model_validate({"items": [rule_card()]})
    with pytest.raises(CorpusError):
        await import_bundle(service.user_store("default", create=True), bundle, service.embedder)


async def test_us_4_3_import_is_all_or_nothing_when_embedding_fails(
    service: CorpusService,
) -> None:
    await service.import_bundle(CorpusBundle.model_validate({"items": [rule_card()]}))
    before = service.view().items
    failing = Embedder(
        static_models("http://127.0.0.1:9/v1"),
        transport=httpx.MockTransport(lambda _r: httpx.Response(503)),
    )
    later = CorpusBundle.model_validate(
        {"items": [rule_card(TODAY - timedelta(days=1)), *other_items()]}
    )
    with pytest.raises(ModelUnavailableError):
        await import_bundle(service.global_store(), later, failing)
    assert service.view().items == before


def test_us_4_3_bundle_must_be_a_bounded_regular_file(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.yaml"
    os.mkfifo(fifo)
    with pytest.raises(BundleError, match="regular file"):
        parse_bundle(fifo)  # returns at once: no writer is waited for
    huge = [rule_card(title=f"Card {i}", payer=f"Payer {i}", body="x" * 200_000) for i in range(30)]
    with pytest.raises(ValidationError, match="5 MiB"):
        CorpusBundle.model_validate({"items": huge})  # the worker route enforces it too


# --- Hermes registration ------------------------------------------------------------------------


def test_us_4_3_hermes_cli_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    registrar = FakeRegistrar()
    load_agent_half().register(registrar)
    entry = registrar.cli_commands[cli.COMMAND]
    assert "corpus" in entry["help"]
    parser = argparse.ArgumentParser(prog="hermes claimcoach")
    entry["setup_fn"](parser)
    parsed = parser.parse_args(["corpus", "import", "rules.yaml"])
    assert (parsed.claimcoach_group, parsed.claimcoach_command, parsed.file) == (
        "corpus",
        "import",
        Path("rules.yaml"),
    )
    assert not hasattr(parsed, "command")  # Hermes' own top-level dest stays untouched
    seen: list[str] = []

    def fake_run(parsed_args: argparse.Namespace) -> int:
        seen.append(parsed_args.claimcoach_command)
        return 0

    monkeypatch.setattr(cli, "run", fake_run)
    entry["handler_fn"](parsed)
    monkeypatch.setattr(cli, "run", lambda _a: 1)
    with pytest.raises(SystemExit) as exited:
        entry["handler_fn"](parsed)
    assert exited.value.code == 1
    assert seen == ["import"]


@pytest.mark.hermes
def test_us_4_3_real_hermes_registers_cli(hermes_python: Path, tmp_path: Path) -> None:
    """The real Hermes loader registers ``hermes claimcoach`` once the plugin is enabled."""
    assert probe_hermes(hermes_python, tmp_path / "off", enabled=False)["cli_commands"] == []
    assert probe_hermes(hermes_python, tmp_path / "on", enabled=True)["cli_commands"] == [
        cli.COMMAND
    ]


@pytest.mark.hermes
def test_us_4_3_hermes_claimcoach_corpus_import_help(hermes_python: Path, tmp_path: Path) -> None:
    """``hermes claimcoach corpus import`` parses through the real Hermes CLI entry point."""
    probe_hermes(hermes_python, tmp_path, enabled=True)  # writes the throwaway HERMES_HOME
    home = tmp_path / "hermes-home"
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONPATH": str(HERMES_ROOT)}
    done = subprocess.run(
        [str(hermes_python), "-m", "hermes_cli.main", "claimcoach", "corpus", "import", "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert "usage: hermes claimcoach corpus import [-h] [--port PORT] file" in done.stdout


# --- The other CLI subcommands ------------------------------------------------------------------


def test_us_4_3_cli_worker_commands(
    tmp_path: Path, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    store = service.user_store("default", create=True)
    add_case_document(store, "c1", "Denied CO-197.", closed_days_ago=120)
    with corpus_client(service) as (client, _):
        code, out = run_cli(client, "corpus", "status")
        assert code == 0
        assert json.loads(out[0])["user_scopes"][0]["profile"] == "default"
        code, out = run_cli(client, "corpus", "reindex", "--scope", "user")
        assert (code, json.loads(out[0])["chunks"]) == (0, 1)
        code, out = run_cli(client, "corpus", "audit", "--case", "c1")
        assert code == 0
        assert [e["action"] for e in json.loads(out[0])["entries"]] == [
            "case_created",
            "document_added",
            "case_closed",
        ]
        code, out = run_cli(client, "corpus", "purge")
        assert (code, json.loads(out[0])["reports"][0]["cases"]) == (0, ["c1"])
        code, out = run_cli(client, "corpus", "purge", "--case", "c1")
        assert (code, out) == (2, ["error: invalid arguments"])
        code, out = run_cli(client, "corpus", "audit", "--profile", "nobody", "--case", "zz")
        assert (code, out) == (1, ["error: profile_not_found"])
    assert not (tmp_path / "hermes" / "profiles" / "nobody").exists()  # a typo creates nothing


def test_us_4_3_cli_worker_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = write_bundle(tmp_path / "rules.yaml", [rule_card()])
    offline = WorkerClient("http://127.0.0.1:9", lambda: None)
    out = Lines()
    assert cli.run(args("corpus", "import", str(bundle)), client=offline, out=out) == 1
    assert out == ["error: worker_unavailable"]
    # Without a client, the CLI builds one for this Hermes root's worker: none runs here.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    out = Lines()
    assert cli.run(args("corpus", "list"), out=out) == 1
    assert out == ["error: worker_unavailable"]


def test_us_4_3_cli_backup_and_restore(
    tmp_path: Path, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "hermes"
    monkeypatch.setenv("HERMES_HOME", str(root))
    add_case_document(service.user_store("default", create=True), "c1", "Appeal for denied MRI.")
    out = Lines()
    assert cli.run(args("corpus", "backup", "--to", str(tmp_path / "bk")), out=out) == 0
    folder = Path(out[0].removeprefix("backed up to "))
    service.close()

    out = Lines()
    assert cli.run(args("corpus", "restore", "--from", str(folder)), out=out) == 2
    assert out == ["error: restore replaces the corpus scopes; re-run with --confirm"]
    monkeypatch.setattr(cli, "worker_status", lambda _config: object())
    out = Lines()
    assert cli.run(args("corpus", "restore", "--from", str(folder), "--confirm"), out=out) == 2
    assert out == ["error: stop the worker first (make stop)"]
    monkeypatch.setattr(cli, "worker_status", lambda _config: None)
    out = Lines()
    assert cli.run(args("corpus", "restore", "--from", str(folder), "--confirm"), out=out) == 0
    assert out == ["restored user-default"]
    out = Lines()
    assert cli.run(args("corpus", "backup", "--to", str(tmp_path / "x")), out=out) == 0


def test_us_4_3_cli_module_entry_point(tmp_path: Path) -> None:
    """``python -m claimcoach.cli`` (the Makefile's entry) runs ``main``."""
    env = {**os.environ, "HERMES_HOME": str(tmp_path), "PYTHONPATH": str(REPO_ROOT / "plugin")}
    done = subprocess.run(
        [sys.executable, "-m", "claimcoach.cli", "corpus", "backup", "--to", str(tmp_path / "b")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 2
    assert done.stdout.strip() == "error: no corpus scope to back up"
    assert list(tmp_path.iterdir()) == []  # a refused backup creates nothing under HERMES_HOME
    assert cli.main(["corpus", "backup", "--to", str(tmp_path / "b")]) == 2


async def test_us_4_3_client_corpus_calls(service: CorpusService) -> None:
    service.user_store("default", create=True)
    with corpus_client(service) as (client, _):
        view = await client.corpus_view()
        assert view.items == []
        audit = await client.corpus_audit("default", "c9")
        assert audit.entries == []


# --- Fix: the corpus CLI honors WORKER_PORT (fix-corpus-cli-worker-port) -------------------------


def corpus_cli(*argv: str) -> tuple[int, list[str]]:
    """Run ``python -m claimcoach.cli corpus …`` in-process, as ``make corpus-*`` does."""
    lines: list[str] = []
    code = cli.run(cli.build_parser().parse_args(["corpus", *argv]), out=lines.append)
    return code, lines


def running_worker_at(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    """Make the launcher report a running worker on ``port`` (its PID file, as ``start`` writes)."""
    handle = WorkerHandle(
        pid=os.getpid(),
        base_url=f"http://127.0.0.1:{port}",
        token_path=WorkerConfig(data_dir=app_data_dir()).token_path,
        started_at=datetime.now(UTC),
    )
    monkeypatch.setattr(cli, "worker_status", lambda _config: handle)


def test_us_4_3_corpus_cli_reaches_a_worker_on_another_port(
    tmp_path: Path, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker on 18201-18219 is reached with ``--port``, as ``make WORKER_PORT=…`` passes it."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    token = issue_token(WorkerConfig(data_dir=app_data_dir()).token_path)
    bundle = write_bundle(tmp_path / "rules.yaml", [rule_card()])
    port = free_port_in_range(18201)
    running_worker_at(monkeypatch, port)
    with LiveApp(create_app(token, corpus=service), port=port) as live:
        assert live.port == port
        imported = corpus_cli("import", str(bundle), "--port", str(port))
        listed = corpus_cli("list", "--port", str(port))
    assert imported == (0, ["imported 1 rule_card (1 chunks)"])
    assert listed[0] == 0
    assert any("Aetna/timely_filing" in line for line in listed[1])


@pytest.mark.parametrize("recorded", [18200, None])
def test_us_4_3_corpus_cli_sends_the_token_only_to_the_recorded_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: int | None
) -> None:
    """Review regression: a ``--port`` that names another process (a model server, a mistyped
    port) or no running worker gets no request, so the token never leaves for it."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    issue_token(WorkerConfig(data_dir=app_data_dir()).token_path)
    if recorded is None:
        monkeypatch.setattr(cli, "worker_status", lambda _config: None)
    else:
        running_worker_at(monkeypatch, recorded)
    seen: list[str] = []
    listener = FastAPI()

    @listener.middleware("http")
    async def record(request: Any, call_next: Any) -> Any:
        seen.append(request.headers.get("authorization", ""))
        return await call_next(request)

    port = free_port_in_range(18201)
    with LiveApp(listener, port=port):
        assert corpus_cli("list", "--port", str(port)) == (1, ["error: worker_unavailable"])
    assert seen == [], "nothing was sent to the other port"


def test_us_4_3_corpus_cli_port_defaults_and_scope() -> None:
    parser = cli.build_parser()
    for command in (
        ["import", "x.yaml"],
        ["list"],
        ["status"],
        ["reindex", "--scope", "global"],
        ["purge"],
        ["audit"],
    ):
        assert parser.parse_args(["corpus", *command]).port == 18200, command
        assert parser.parse_args(["corpus", *command, "--port", "18219"]).port == 18219
    for local in (
        ["backup", "--to", "d"],
        ["restore", "--from", "d"],
        ["key-export", "--to", "k"],
        ["key-import", "--from", "k"],
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(["corpus", *local, "--port", "18201"])


@pytest.mark.parametrize("port", ["80", "18220", "18199", "abc", "-1"])
def test_us_4_3_corpus_cli_refuses_a_port_outside_the_range(
    port: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        cli.main(["corpus", "list", "--port", port])
    assert exited.value.code == 2
    assert "not a ClaimCoach port (18200-18219)" in capsys.readouterr().err


def test_us_4_3_corpus_targets_pass_worker_port() -> None:
    def dry(target: str, *extra: str) -> str:
        return subprocess.run(
            ["make", "-n", target, "WORKER_PORT=18213", *extra],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "HERMES_HOME": "/nonexistent"},
        ).stdout

    for target, extra in (
        ("corpus-status", ()),
        ("corpus-list", ()),
        ("corpus-import", ("FILE=Makefile",)),
        ("corpus-reindex", ("SCOPE=global",)),
        ("corpus-purge", ()),
        ("corpus-audit", ()),
    ):
        assert "--port 18213" in dry(target, *extra), target
    local: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("corpus-backup", ()),
        ("corpus-restore", ("FROM=/nonexistent", "CONFIRM=yes")),
        ("corpus-key-export", ("TO=/nonexistent/key",)),
        ("corpus-key-import", ("FROM=/nonexistent/key", "CONFIRM=yes")),
    )
    for name, settings in local:
        assert "--port" not in dry(name, *settings), "the local commands take no port"


def test_us_4_3_corpus_runbook_names_the_worker_port() -> None:
    runbook = (REPO_ROOT / "docs/runbooks/corpus-import-reindex-backup-restore.md").read_text()
    for fact in ("WORKER_PORT", "--port", "always use 18200", "its own `HERMES_HOME`"):
        assert fact in runbook, fact
