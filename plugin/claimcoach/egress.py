"""Record every attempt a process makes to reach beyond loopback.

Implements: US-12.4 (the socket audit hook: ``EgressAudit`` sees each ``socket.connect``,
``socket.sendto``, and ``socket.getaddrinfo`` audit event, and passes those naming a non-loopback
address to a sink as an ``EgressRecord``; the worker writes them to ``worker/egress.jsonl``).
Rules: BR-1 and NFR-5 (an outbound call is measured, not assumed), BR-14 (a record holds the
destination, the event, and the time only: never a payload or a document).

An audit hook cannot be removed once added (PEP 578), so a process installs one hook for its
lifetime and ``start``/``stop`` only switch where its records go. The hook never raises into the
socket call it observes: a record it cannot write is counted (``dropped``), and the worker reports
both facts at ``GET /egress`` so the US-12.4 check refuses a worker that is not recording.
Loopback traffic, which is all a case flow needs, returns from the hook before anything is built.
Only stdlib and Pydantic are imported, so the gateway and the worker can both use it.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

__all__ = [
    "EGRESS_AUDIT",
    "EGRESS_LOG",
    "EgressAudit",
    "EgressEvent",
    "EgressRecord",
    "EgressStatus",
    "file_sink",
    "is_loopback",
    "read_records",
]

EGRESS_LOG: Final = "egress.jsonl"
"""The worker's record file, in its state dir next to the token (mode 0600)."""

EgressEvent = Literal["connect", "sendto", "resolve"]
"""What the process tried: open a connection, send a datagram, or look up a host name."""

_EVENTS: Final[dict[str, EgressEvent]] = {
    "socket.connect": "connect",
    "socket.sendto": "sendto",
    "socket.getaddrinfo": "resolve",
}


def is_loopback(host: object) -> bool:
    """Return whether ``host`` names this machine (IPv4/IPv6 loopback or ``localhost``).

    Args:
        host: A host as a socket call receives it: text, bytes, or anything else (never loopback).
    """
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


class EgressStatus(BaseModel):
    """``GET /egress`` on the worker: whether its audit hook records, and what it lost.

    Attributes:
        ok: Always ``True``.
        audit: The hook passes records to ``worker/egress.jsonl``.
        dropped: Attempts it saw but could not record since the worker started.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    audit: bool
    dropped: int = Field(ge=0)


class EgressRecord(BaseModel):
    """One attempt to reach a non-loopback address.

    Attributes:
        at: When it happened (UTC).
        process: Which ClaimCoach process made it (``worker``, ``plugin_api``).
        pid: Its process ID.
        event: What it tried.
        host: The destination host or address.
        port: The destination port, when the call named one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    at: datetime
    process: str = Field(min_length=1, max_length=32)
    pid: int = Field(ge=0)
    event: EgressEvent
    host: str = Field(max_length=255)
    port: int | None = None


Sink = Callable[[EgressRecord], None]
AuditHook = Callable[[str, tuple[object, ...]], None]
_RECORD: Final = TypeAdapter(EgressRecord)


def _destination(event: EgressEvent, args: tuple[object, ...]) -> tuple[object, object] | None:
    """The ``(host, port)`` an audit event names, or ``None`` for a local (Unix) socket."""
    if event == "resolve":
        return args[0], args[1]
    sock, address = args[0], args[1]
    if isinstance(sock, socket.socket) and sock.family == socket.AF_UNIX:
        return None
    if isinstance(address, tuple) and address:
        return address[0], address[1] if len(address) > 1 else None
    return address, None


def _port(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str | bytes) and value.isdigit():
        return int(value)
    return None


class EgressAudit:
    """The process's one socket audit hook and where its records go.

    Args:
        add_hook: ``sys.addaudithook`` (tests pass a recorder).
    """

    def __init__(self, add_hook: Callable[[AuditHook], None]) -> None:
        """Keep ``add_hook``; the hook is added on the first ``start``."""
        self._add_hook = add_hook
        self._installed = False
        self._sink: Sink | None = None
        self._process = ""
        self._lock = threading.Lock()
        self.dropped = 0
        """Attempts seen but not recorded because the sink failed (a full disk); never reset."""

    @property
    def active(self) -> bool:
        """Whether records are being passed to a sink."""
        return self._sink is not None

    def status(self) -> EgressStatus:
        """This process's audit state, for ``GET /egress`` on the worker."""
        return EgressStatus(audit=self.active, dropped=self.dropped)

    def start(self, process: str, sink: Sink) -> None:
        """Pass this process's non-loopback attempts, labeled ``process``, to ``sink``.

        Args:
            process: The label records carry (``worker``, ``plugin_api``).
            sink: Called once per attempt, on the thread that made it. If it raises, the attempt
                is counted in ``dropped`` and the caller's socket call goes on.
        """
        with self._lock:
            if not self._installed:
                self._add_hook(self._hook)
                self._installed = True
            self._process, self._sink = process, sink

    def stop(self) -> None:
        """Stop passing records on (the hook stays, idle)."""
        with self._lock:
            self._sink = None

    def _hook(self, name: str, args: tuple[object, ...]) -> None:
        event = _EVENTS.get(name)
        sink = self._sink
        if event is None or sink is None:
            return
        destination = _destination(event, args)
        if destination is None or destination[0] is None or is_loopback(destination[0]):
            return
        host, port = destination
        text = host.decode(errors="replace") if isinstance(host, bytes) else str(host)
        try:
            sink(
                EgressRecord(
                    at=datetime.now(UTC),
                    process=self._process,
                    pid=os.getpid(),
                    event=event,
                    host=text[:255],
                    port=_port(port),
                )
            )
        except Exception:  # noqa: BLE001 - an audit hook must never break the caller's socket call
            self.dropped += 1


EGRESS_AUDIT: Final = EgressAudit(sys.addaudithook)
"""This process's audit; ``python -m claimcoach.worker`` starts it before serving."""


def file_sink(path: Path) -> Sink:
    """A sink that appends each record as one JSON line to ``path`` (created mode 0600).

    The file is created now, so a folder or permission problem shows before anything is audited.

    Args:
        path: The record file; its folder must exist.

    Raises:
        OSError: The file cannot be created or opened for appending.
    """

    def write(record: EgressRecord) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, record.model_dump_json().encode() + b"\n")
        finally:
            os.close(fd)

    os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600))
    return write


def read_records(path: Path, offset: int = 0) -> list[EgressRecord]:
    """Return the records appended to ``path`` after byte ``offset``.

    Args:
        path: A file ``file_sink`` writes; a missing file holds no records.
        offset: Where to start reading (the file's size when a measurement began).

    Returns:
        The records, oldest first. A line that is not a record (a torn write) is reported as a
        record of host ``unreadable`` so it cannot hide an attempt.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            lines = handle.read().splitlines()
    except FileNotFoundError:
        return []
    records: list[EgressRecord] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            records.append(_RECORD.validate_json(line))
        except ValidationError:
            records.append(
                EgressRecord(
                    at=datetime.now(UTC),
                    process="unknown",
                    pid=0,
                    event="connect",
                    host="unreadable",
                )
            )
    return records
