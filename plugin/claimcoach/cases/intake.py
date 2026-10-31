"""Reading an upload: the single-file multipart body and the kind of its bytes.

Implements: US-5.1 (``parse_upload`` reads the one ``file`` part Hermes' ``ctx.rest`` upload sends,
in memory; ``sniff`` decides ``pdf``, ``image``, ``edi_835``, or ``text`` from the bytes, never from
the filename or the declared type). Rules: ES-8 (each refusal is a ``CaseError`` with one fixed
envelope code), BR-14 (errors carry no content).

Starlette's form parser is not used: it spools parts over 1 MiB to an unencrypted temporary file,
and this body is PHI.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from claimcoach.cases.errors import (
    DocumentTooLargeError,
    MalformedUploadError,
    UnsupportedDocumentError,
)
from claimcoach.cases.models import MAX_FILE_BYTES, SourceKind

__all__ = [
    "UploadedFile",
    "is_edi_835",
    "parse_upload",
    "read_limited",
    "sniff",
    "text_kind",
]

_PDF: Final = b"%PDF-"
_PDF_WINDOW: Final = 1024
"""PDF readers find the ``%PDF-`` header anywhere in a file's first 1024 bytes."""
_IMAGES: Final = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")
_BOUNDARY: Final = re.compile(r';\s*boundary=(?:"([^"]{1,70})"|([^";\s]{1,70}))', re.IGNORECASE)
_PARAM: Final = r';\s*{name}="([^"]*)"'
_ISA_LENGTH: Final = 106
"""The ISA segment is fixed-width; its last character is the segment terminator."""


class UploadedFile(BaseModel):
    """The file part of an upload.

    Attributes:
        filename: Its base name, or ``None`` when the upload named none.
        content_type: The declared media type.
        data: Its bytes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str | None = Field(default=None, min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=127)
    data: bytes = Field(min_length=1)


def _header(headers: dict[str, str], name: str) -> str:
    return headers.get(name, "").strip()


def _headers(block: bytes) -> dict[str, str]:
    try:
        lines = block.decode("utf-8").split("\r\n")
    except UnicodeDecodeError as exc:
        raise MalformedUploadError from exc
    headers: dict[str, str] = {}
    for line in lines:
        name, colon, value = line.partition(":")
        if not colon:
            raise MalformedUploadError
        headers[name.strip().lower()] = value
    return headers


def _filename(disposition: str) -> str | None:
    match = re.search(_PARAM.format(name="filename"), disposition)
    if match is None:
        return None
    # A browser may send a full path; keep the last component of either separator.
    base = PurePosixPath(match.group(1).replace("\\", "/")).name.strip()
    return base[:255] or None


def parse_upload(body: bytes, content_type: str) -> UploadedFile:
    """Return the one ``file`` part of a ``multipart/form-data`` body.

    Args:
        body: The whole request body.
        content_type: The request's ``Content-Type`` header (it names the boundary).

    Returns:
        The file.

    Raises:
        MalformedUploadError: Not exactly one part named ``file``.
        DocumentTooLargeError: The file is over ``MAX_FILE_BYTES``.
        UnsupportedDocumentError: The file is empty.
    """
    media_type = content_type.split(";", 1)[0].strip().lower()
    boundary = _BOUNDARY.search(content_type)
    if media_type != "multipart/form-data" or boundary is None:
        raise MalformedUploadError
    delimiter = b"--" + (boundary.group(1) or boundary.group(2)).encode("latin-1")
    closing = body.rfind(b"\r\n" + delimiter + b"--")
    if not body.startswith(delimiter + b"\r\n") or closing < 0:
        raise MalformedUploadError
    if body[closing + len(delimiter) + 4 :].strip(b"\r\n"):
        raise MalformedUploadError  # nothing but a line break may follow the closing delimiter
    part = body[len(delimiter) + 2 : closing]
    head, separator, data = part.partition(b"\r\n\r\n")
    if not separator or b"\r\n" + delimiter in data:
        raise MalformedUploadError  # no header block, or a second part
    headers = _headers(head)
    disposition = _header(headers, "content-disposition")
    name = re.search(_PARAM.format(name="name"), disposition)
    if not disposition.lower().startswith("form-data") or name is None or name.group(1) != "file":
        raise MalformedUploadError
    if len(data) > MAX_FILE_BYTES:
        raise DocumentTooLargeError
    if not data:
        raise UnsupportedDocumentError
    declared = _header(headers, "content-type")[:127] or "application/octet-stream"
    return UploadedFile(filename=_filename(disposition), content_type=declared, data=data)


def is_edi_835(text: str) -> bool:
    """Return whether ``text`` is an X12 interchange that holds an 835 transaction set.

    The ISA segment fixes the element separator (its 4th character) and the segment terminator
    (its 106th), so any X12 delimiters are read correctly.
    """
    interchange = text.lstrip("﻿ \t\r\n")
    if not interchange.startswith("ISA") or len(interchange) < _ISA_LENGTH:
        return False
    element, terminator = interchange[3], interchange[_ISA_LENGTH - 1]
    return any(
        segment.strip().split(element)[:2] == ["ST", "835"]
        for segment in interchange.split(terminator)
    )


def text_kind(text: str) -> SourceKind:
    """Return ``edi_835`` or ``text`` for a text document.

    Raises:
        UnsupportedDocumentError: The text is blank or holds NUL characters (binary data).
    """
    if not text.strip() or "\x00" in text:
        raise UnsupportedDocumentError
    return "edi_835" if is_edi_835(text) else "text"


def sniff(data: bytes) -> SourceKind:
    """Return the kind of ``data`` from its leading bytes.

    Raises:
        UnsupportedDocumentError: Not a PDF, PNG, JPEG, or UTF-8 text.
    """
    if _PDF in data[:_PDF_WINDOW]:  # readers accept junk (a scanner's prefix) before the header
        return "pdf"
    if data.startswith(_IMAGES):
        return "image"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError from exc
    return text_kind(text)


async def read_limited(chunks: AsyncIterator[bytes], limit: int, declared: str | None) -> bytes:
    """Read a request body of at most ``limit`` bytes into memory.

    Args:
        chunks: The body stream (``Request.stream()``).
        limit: Most bytes accepted.
        declared: The ``Content-Length`` header, checked first so an oversized body is refused
            before it is read.

    Raises:
        DocumentTooLargeError: The body is over ``limit``.
    """
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise DocumentTooLargeError
    parts: list[bytes] = []
    size = 0
    async for chunk in chunks:
        size += len(chunk)
        if size > limit:
            raise DocumentTooLargeError
        parts.append(chunk)
    return b"".join(parts)
