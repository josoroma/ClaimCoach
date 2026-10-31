"""US-1.4 Quality Gate and Test Harnesses.

Scenarios: make check passes on a clean tree; a type error fails the gate; plugin.js is
type-checked against the SDK stub; offline tests use the fake model server. (The registration and
allowed-imports scenarios run under ``node --test`` in ``plugin/desktop/tests/``.) Rules: ES-1,
ES-2, ES-4, ES-7, PC-3.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

import httpx
import pytest

from tests.conftest import REPO_ROOT
from tests.fakes.fake_model_server import DEFAULT_REPLY, FakeModelServer
from tests.fakes.socket_guard import NetworkBlockedError, is_loopback

MAKE = shutil.which("make") or "make"
NPM = shutil.which("npm") or "npm"


def run_make(*args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "COV_CORE"))}
    return subprocess.run(
        [MAKE, "--no-print-directory", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


# --- Scenario: make check passes on a clean tree -----------------------------------------------


@pytest.mark.gate
def test_us_1_4_make_check_passes() -> None:
    result = run_make("check")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-4000:]
    for tool in (
        "ruff check",
        "ruff format --check",
        "biome check",
        "mypy",
        "tsc --noEmit",
        "pytest -m",
        "npm test",
    ):
        assert tool in output, f"make check did not run {tool}"
    assert re.search(r"Required test coverage of 100(\.0)?% reached", output)
    assert re.search(r"plugin\.js\s*\|\s*100\.00\s*\|\s*100\.00\s*\|\s*100\.00", output)


# --- Scenario: A type error fails the gate -----------------------------------------------------


@pytest.mark.gate
def test_us_1_4_type_error_fails_gate(tmp_path: Path) -> None:
    bad = tmp_path / "bad_return.py"
    bad.write_text('def answer() -> int:\n    return "forty-two"\n')
    result = run_make("check", f"MYPY_EXTRA={bad}")
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert re.search(r"bad_return\.py:2: error: Incompatible return value type", output), output


# --- Scenario: plugin.js is type-checked against the SDK stub ----------------------------------


def test_us_1_4_plugin_js_typechecks() -> None:
    if not (REPO_ROOT / "node_modules" / ".bin" / "tsc").exists():
        pytest.fail("node_modules missing: run make install")
    result = subprocess.run(
        [NPM, "exec", "--no", "--", "tsc", "--noEmit", "-p", "tsconfig.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == ""
    stub = (REPO_ROOT / "types" / "hermes-plugin-sdk.d.ts").read_text()
    assert "desktop-plugin-sdk.md" in stub, "the stub cites the SDK docs it was checked against"


# --- Scenario: Offline tests use the fake model server -----------------------------------------


def test_us_1_4_offline_tests_use_fake_server(fake_model_server: FakeModelServer) -> None:
    assert fake_model_server.base_url.startswith("http://127.0.0.1:")
    with httpx.Client(base_url=fake_model_server.base_url) as client:
        models = client.get("/models").json()
        reply = client.post(
            "/chat/completions",
            json={"model": "qwen3-8b", "messages": [{"role": "user", "content": "classify"}]},
        ).json()
        unknown = client.post(
            "/chat/completions",
            json={"model": "other", "messages": [{"role": "user", "content": "hi"}]},
        ).json()
    assert [m["id"] for m in models["data"]] == ["qwen3-8b"]
    assert reply["choices"][0]["message"]["content"] == '{"label": "CO-197"}'
    assert unknown["choices"][0]["message"]["content"] == DEFAULT_REPLY
    assert [r.model for r in fake_model_server.requests[-2:]] == ["qwen3-8b", "other"]


def test_us_1_4_fake_server_without_replies_lists_placeholder_model() -> None:
    with FakeModelServer() as server:
        models = httpx.get(f"{server.base_url}/models").json()
    assert [m["id"] for m in models["data"]] == ["fake-model"]


def test_us_1_4_socket_guard_blocks_non_loopback() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NetworkBlockedError):
            sock.connect(("10.255.255.1", 80))
        with pytest.raises(NetworkBlockedError):
            sock.connect_ex(("93.184.216.34", 443))
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(NetworkBlockedError):
        httpx.get("https://example.com", timeout=1)


def test_us_1_4_socket_guard_allows_loopback_and_unix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert socket.getaddrinfo("localhost", 80)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        assert sock.connect_ex(("127.0.0.1", 9)) != 0  # refused, but not blocked
    monkeypatch.chdir(tmp_path)  # relative path: macOS caps AF_UNIX paths at 104 bytes
    path = Path("s.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        server.listen()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(path))


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.8.9.10", True),
        ("::1", True),
        ("fe80::1%lo0", False),
        ("localhost", True),
        (b"127.0.0.1", True),
        ("10.0.0.1", False),
        ("example.com", False),
        (None, False),
    ],
)
def test_us_1_4_is_loopback(host: object, expected: bool) -> None:
    assert is_loopback(host) is expected


# --- Coverage honesty --------------------------------------------------------------------------


def test_us_1_4_no_coverage_exclusions() -> None:
    """100% coverage must be earned: no pragma or ignore comments in shipped code or tools."""
    pattern = re.compile(r"pragma:\s*no\s*cover|istanbul ignore|c8 ignore|node:coverage")
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for root in ("plugin", "tools")
        for path in (REPO_ROOT / root).rglob("*")
        if path.suffix in {".py", ".js", ".mjs"} and pattern.search(path.read_text())
    ]
    assert offenders == []
