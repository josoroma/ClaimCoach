"""Socket guard: offline tests may only talk to loopback.

Implements: US-1.4 ("no test opens a network connection to a non-loopback address"). Rules: G-5,
NFR-5 (zero outbound calls carrying case content) — enforced in tests; US-12.4 measures it in
the running app with the same ``is_loopback``.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from claimcoach.egress import is_loopback

__all__ = ["NetworkBlockedError", "install", "is_loopback"]


class NetworkBlockedError(RuntimeError):
    """A test tried to reach a non-loopback address.

    Deliberately not an ``OSError``: httpx would map an ``OSError`` to ``ConnectError`` and a test
    of "worker unavailable" could pass for the wrong reason.
    """


def install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``socket`` so connects and DNS lookups outside loopback raise.

    Args:
        monkeypatch: The test's monkeypatch; the patch is undone after the test.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def check(sock: socket.socket, address: Any) -> None:
        if sock.family == socket.AF_UNIX:
            return
        host = address[0] if isinstance(address, tuple) else address
        if not is_loopback(host):
            raise NetworkBlockedError(f"offline test tried to connect to {address!r}")

    def connect(self: socket.socket, address: Any) -> None:
        check(self, address)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        check(self, address)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host is not None and not is_loopback(host):
            raise NetworkBlockedError(f"offline test tried to resolve {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
