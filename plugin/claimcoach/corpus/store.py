"""One corpus scope on disk: a WAL SQLite database and its own vector index.

Implements: US-4.1 (``CorpusStore``: ``corpus.sqlite3`` + ``index.sqlite3`` per scope; the index
records its embedding model and refuses searches and inserts once that model changes), US-4.2
(user-scope bodies, chunks, and vectors are encrypted per row; a key check fails closed), US-4.4
(user-scope ``search`` and ``chunks`` require a ``case_id`` and filter in SQL), US-4.5
(``close_case``, de-identified ``outcomes``, ``purge_case_content``), US-4.6 (append-only
``audit_log``; ``open_case`` audits), US-5.1 (``case_items``: a case's attached source files and
derived items, sealed per row, refused once the case is closed, deleted by the purge). Rules: BR-5,
BR-6, BR-7, BR-13, BR-14.

Both files use ``secure_delete`` so deleted PHI pages are zeroed, and a purge truncates the WAL.
Vectors are float32, normalized to unit length, so cosine similarity is a dot product.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

from claimcoach.corpus.crypto import Cipher
from claimcoach.corpus.errors import (
    CaseClosedError,
    CaseNotFoundError,
    CorpusError,
    CorpusKeyError,
    IndexStaleError,
)
from claimcoach.corpus.paths import DATABASE, INDEX
from claimcoach.corpus.types import (
    AuditAction,
    AuditEntry,
    CaseItem,
    CaseItemKind,
    CaseOutcome,
    CaseRecord,
    Chunk,
    CorpusScope,
    Document,
    IndexInfo,
    OutcomeRecord,
    ScopeStatus,
    utc_now,
)
from claimcoach.logs import get_logger

__all__ = ["CorpusStore", "Vectors", "split_text"]

CHUNK_CHARS: Final = 1200
"""Characters per chunk (~300 tokens), cut at paragraph, then line, then word boundaries."""

_KEY_CHECK: Final = b"claimcoach user store"
_log = get_logger("claimcoach.corpus")

Vectors = npt.NDArray[np.float32]
"""A ``(n, dimension)`` float32 matrix."""

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS main.meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS main.cases (
    case_id TEXT PRIMARY KEY, opened_at TEXT NOT NULL, closed_at TEXT, purged_at TEXT
) STRICT;
CREATE TABLE IF NOT EXISTS main.documents (
    doc_id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(case_id), kind TEXT NOT NULL,
    created_at TEXT NOT NULL, body BLOB NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS main.documents_case ON documents(case_id);
CREATE TABLE IF NOT EXISTS main.chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    case_id TEXT, kind TEXT NOT NULL, ordinal INTEGER NOT NULL, body BLOB NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS main.chunks_case ON chunks(case_id);
CREATE INDEX IF NOT EXISTS main.chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS main.outcomes (
    case_id TEXT PRIMARY KEY REFERENCES cases(case_id),
    outcome TEXT NOT NULL CHECK (outcome IN ('overturned', 'upheld', 'written_off')),
    recorded_at TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS main.case_items (
    case_id TEXT NOT NULL REFERENCES cases(case_id), item_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('source', 'extraction')), created_at TEXT NOT NULL,
    payload BLOB NOT NULL, data BLOB, PRIMARY KEY (case_id, item_id)
) STRICT;
CREATE TABLE IF NOT EXISTS main.audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, action TEXT NOT NULL,
    case_id TEXT NOT NULL, profile TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS main.audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS main.audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS main.audit_log_no_overwrite BEFORE INSERT ON audit_log
WHEN EXISTS (SELECT 1 FROM audit_log WHERE seq = NEW.seq)
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TABLE IF NOT EXISTS idx.meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS idx.vectors (
    chunk_id TEXT PRIMARY KEY, case_id TEXT, vector BLOB NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx.vectors_case ON vectors(case_id);
"""


def _touch_private(path: Path) -> None:
    """Create ``path`` with mode 0600 so SQLite's WAL and SHM files inherit owner-only access."""
    os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    path.chmod(0o600)


def _split(text: str, size: int, separators: Sequence[str]) -> list[str]:
    if len(text) <= size:
        return [text]
    if not separators:
        return [text[start : start + size] for start in range(0, len(text), size)]
    separator, rest = separators[0], separators[1:]
    pieces: list[str] = []
    current = ""
    for part in text.split(separator):
        candidate = f"{current}{separator}{part}" if current else part
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            pieces.append(current)
        if len(part) <= size:
            current = part
        else:
            pieces += _split(part, size, rest)
            current = ""
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split ``text`` into chunks of at most ``size`` characters; blank pieces are dropped.

    Args:
        text: Document text.
        size: Maximum characters per chunk.

    Returns:
        The chunks, in document order.
    """
    return [piece.strip() for piece in _split(text, size, ("\n\n", "\n", " ")) if piece.strip()]


def _normalized(vectors: Vectors) -> Vectors:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)


def _iso(value: datetime) -> str:
    """Stored timestamps are UTC, so their ISO strings sort in time order."""
    return value.astimezone(UTC).isoformat()


def _ctx(table: str, case_id: str | None, row_id: str) -> str:
    """Associated data: a sealed value only opens as this row of this case."""
    return f"{table}:{case_id or ''}:{row_id}"


class CorpusStore:
    """A scope's database and vector index.

    Args:
        directory: The scope directory (see ``claimcoach.corpus.paths``).
        scope: Which scope this is; recorded on first open and checked afterwards.
        embedding_model_id: Embedding model ``models.yaml`` configures now.
        cipher: Required in the user scope, refused in the global scope.
        profile: Hermes profile of a user scope; recorded in audit entries.

    Raises:
        CorpusError: The files cannot be opened or belong to another scope.
        CorpusKeyError: ``cipher`` does not decrypt this user store.
    """

    def __init__(
        self,
        directory: Path,
        scope: CorpusScope,
        *,
        embedding_model_id: str,
        cipher: Cipher | None = None,
        profile: str | None = None,
    ) -> None:
        """Open (creating on first use) the scope's two files."""
        user = scope is CorpusScope.USER
        if (cipher is not None) != user or (profile is not None) != user:
            raise CorpusError("the user scope needs a cipher and a profile; global takes neither")
        self.directory = directory
        self.scope = scope
        self.profile = profile
        self.embedding_model_id = embedding_model_id
        self._cipher = cipher
        self._lock = threading.RLock()
        db: sqlite3.Connection | None = None
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            for name in (DATABASE, INDEX):
                _touch_private(directory / name)
            # Autocommit: transactions are explicit (``_tx``). The worker serves from one event
            # loop, but tests drive the app from a portal thread, hence check_same_thread off.
            db = sqlite3.connect(
                directory / DATABASE, isolation_level=None, check_same_thread=False
            )
            self._db = db
            db.execute("ATTACH DATABASE ? AS idx", (str(directory / INDEX),))
            for schema in ("main", "idx"):
                db.execute(f"PRAGMA {schema}.journal_mode=WAL")
                db.execute(f"PRAGMA {schema}.secure_delete=ON")
                db.execute(f"PRAGMA {schema}.synchronous=NORMAL")
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(_SCHEMA)
            self._init_meta()
        except (sqlite3.Error, OSError, CorpusError) as exc:
            if db is not None:
                db.close()  # a store that failed to open holds no connection
            if isinstance(exc, CorpusError):
                raise
            raise CorpusError from exc

    # --- lifecycle --------------------------------------------------------------------------

    def close(self) -> None:
        """Close the connection."""
        with self._lock:
            self._db.close()

    def __enter__(self) -> CorpusStore:
        """Use the store as a context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the store."""
        self.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def _init_meta(self) -> None:
        with self._tx() as db:
            row = db.execute("SELECT value FROM main.meta WHERE key = 'scope'").fetchone()
            if row is None:
                db.execute("INSERT INTO main.meta VALUES ('scope', ?)", (self.scope.value,))
            elif row[0] != self.scope.value:
                raise CorpusError("these files belong to another scope")
            if self._cipher is not None:
                check = db.execute("SELECT value FROM main.meta WHERE key = 'key_check'").fetchone()
                if check is None:
                    sealed = self._cipher.encrypt(_KEY_CHECK, "meta:key_check").hex()
                    db.execute("INSERT INTO main.meta VALUES ('key_check', ?)", (sealed,))
                else:
                    try:
                        sealed_check = bytes.fromhex(check[0])
                    except ValueError as exc:
                        raise CorpusKeyError from exc
                    self._cipher.decrypt(sealed_check, "meta:key_check")
            db.execute(
                "INSERT OR IGNORE INTO idx.meta VALUES ('embedding_model_id', ?)",
                (self.embedding_model_id,),
            )
            # Vectors whose chunk is gone (a crash between the two files' commits).
            db.execute(
                "DELETE FROM idx.vectors WHERE chunk_id NOT IN (SELECT chunk_id FROM main.chunks)"
            )

    # --- sealing ----------------------------------------------------------------------------

    def _seal(self, data: bytes, context: str) -> bytes:
        return data if self._cipher is None else self._cipher.encrypt(data, context)

    def _unseal(self, blob: bytes, context: str) -> bytes:
        return blob if self._cipher is None else self._cipher.decrypt(blob, context)

    def _require_case_filter(self, case_id: str | None) -> None:
        if (self.scope is CorpusScope.USER) != (case_id is not None):
            raise CorpusError("user-scope reads name one case; global-scope reads name none")

    # --- the vector index -------------------------------------------------------------------

    def _index_meta(self, db: sqlite3.Connection) -> dict[str, str]:
        return dict(db.execute("SELECT key, value FROM idx.meta").fetchall())

    def index_info(self) -> IndexInfo:
        """Return what the vector index was built with and whether it needs a reindex."""
        with self._lock:
            meta = self._index_meta(self._db)
            (count,) = self._db.execute("SELECT count(*) FROM idx.vectors").fetchone()
            (missing,) = self._db.execute(
                "SELECT count(*) FROM main.chunks "
                "WHERE chunk_id NOT IN (SELECT chunk_id FROM idx.vectors)"
            ).fetchone()
        dimension = meta.get("dimension")
        return IndexInfo(
            embedding_model_id=meta["embedding_model_id"],
            configured_model_id=self.embedding_model_id,
            dimension=None if dimension is None else int(dimension),
            vectors=count,
            missing_vectors=missing,
            needs_reindex=meta["embedding_model_id"] != self.embedding_model_id or missing > 0,
        )

    def _require_fresh(self, db: sqlite3.Connection, dimension: int) -> None:
        meta = self._index_meta(db)
        if meta["embedding_model_id"] != self.embedding_model_id:
            raise IndexStaleError
        recorded = meta.get("dimension")
        if recorded is None:
            db.execute("INSERT INTO idx.meta VALUES ('dimension', ?)", (str(dimension),))
        elif int(recorded) != dimension:
            raise IndexStaleError

    def _insert_vectors(
        self, db: sqlite3.Connection, ids: Sequence[tuple[str, str | None]], vectors: Vectors
    ) -> None:
        for (chunk_id, case_id), vector in zip(ids, _normalized(vectors), strict=True):
            blob = self._seal(vector.astype("<f4").tobytes(), _ctx("vectors", case_id, chunk_id))
            db.execute("INSERT INTO idx.vectors VALUES (?, ?, ?)", (chunk_id, case_id, blob))

    def search(
        self, vector: Vectors, n: int, case_id: str | None = None
    ) -> list[tuple[str, float]]:
        """Return the ``n`` chunks nearest to ``vector`` by cosine similarity.

        Args:
            vector: The query embedding, shape ``(dimension,)``.
            n: How many to return.
            case_id: Required in the user scope: only that case's vectors are read and decrypted
                (BR-5). Refused in the global scope.

        Returns:
            ``(chunk_id, similarity)`` pairs, most similar first.

        Raises:
            IndexStaleError: The index was built with another model or dimension.
        """
        self._require_case_filter(case_id)
        with self._lock:
            meta = self._index_meta(self._db)
            if meta["embedding_model_id"] != self.embedding_model_id:
                raise IndexStaleError
            if meta.get("dimension") not in (None, str(vector.shape[-1])):
                raise IndexStaleError
            rows = self._db.execute(
                "SELECT chunk_id, vector FROM idx.vectors WHERE case_id IS ? ORDER BY chunk_id",
                (case_id,),
            ).fetchall()
        if not rows:
            return []
        ids = [chunk_id for chunk_id, _ in rows]
        matrix = np.stack(
            [
                np.frombuffer(self._unseal(blob, _ctx("vectors", case_id, chunk_id)), dtype="<f4")
                for chunk_id, blob in rows
            ]
        )
        query = _normalized(vector.reshape(1, -1).astype(np.float32))[0]
        scores = matrix @ query
        order = np.argsort(-scores, kind="stable")[:n]
        return [(ids[i], float(scores[i])) for i in order]

    def reindex_items(self) -> list[tuple[str, str]]:
        """Return every ``(chunk_id, text)`` of the scope, for a reindex only."""
        with self._lock:
            rows = self._db.execute(
                "SELECT chunk_id, case_id, body FROM main.chunks ORDER BY chunk_id"
            ).fetchall()
        return [
            (chunk_id, self._unseal(body, _ctx("chunks", case_id, chunk_id)).decode())
            for chunk_id, case_id, body in rows
        ]

    def replace_index(self, chunk_ids: Sequence[str], vectors: Vectors) -> None:
        """Replace every vector with ``vectors`` and record the configured embedding model.

        Args:
            chunk_ids: Every chunk of the scope, in the order of ``reindex_items``.
            vectors: Their new embeddings.

        Raises:
            CorpusError: ``chunk_ids`` is not the scope's chunk set.
        """
        with self._tx() as db:
            known = dict(db.execute("SELECT chunk_id, case_id FROM main.chunks").fetchall())
            if sorted(known) != sorted(chunk_ids) or len(chunk_ids) != len(vectors):
                raise CorpusError("reindex input does not match the stored chunks")
            db.execute("DELETE FROM idx.vectors")
            db.execute("DELETE FROM idx.meta WHERE key = 'dimension'")
            db.execute(
                "UPDATE idx.meta SET value = ? WHERE key = 'embedding_model_id'",
                (self.embedding_model_id,),
            )
            if chunk_ids:
                self._require_fresh(db, int(vectors.shape[1]))
                self._insert_vectors(db, [(i, known[i]) for i in chunk_ids], vectors)

    # --- documents and chunks ---------------------------------------------------------------

    def put_document(self, document: Document, chunks: Sequence[str], vectors: Vectors) -> int:
        """Store one document with its chunks and vectors; see ``put_documents``."""
        return self.put_documents([(document, chunks, vectors)])

    def put_documents(self, entries: Sequence[tuple[Document, Sequence[str], Vectors]]) -> int:
        """Store documents with their chunks and vectors in one transaction (all or nothing).

        A document with the ID of a stored one replaces it, with its chunks and vectors.

        Args:
            entries: ``(document, chunk texts in order, one embedding per chunk)`` each.

        Returns:
            Chunks stored.

        Raises:
            CaseNotFoundError: A document's case does not exist.
            IndexStaleError: The index was built with another model or dimension.
            CorpusError: A document belongs to the other scope, or its counts differ.
        """
        for document, chunks, vectors in entries:
            if document.scope is not self.scope or len(chunks) != len(vectors) or not chunks:
                raise CorpusError("document, chunks, and vectors do not fit this store")
        with self._tx() as db:
            for document, chunks, vectors in entries:
                self._put(db, document, chunks, vectors)
        return sum(len(chunks) for _, chunks, _ in entries)

    def _put(
        self, db: sqlite3.Connection, document: Document, chunks: Sequence[str], vectors: Vectors
    ) -> None:
        self._require_fresh(db, int(vectors.shape[1]))
        if document.case_id is not None:
            self._case_row(db, document.case_id)
        owner = db.execute(
            "SELECT case_id FROM main.documents WHERE doc_id = ?", (document.doc_id,)
        ).fetchone()
        if owner is not None and owner[0] != document.case_id:
            raise CorpusError("a document ID belongs to one case")
        self._delete_documents(db, [document.doc_id])
        payload = json.dumps(
            {"title": document.title, "text": document.text, "metadata": document.metadata}
        ).encode()
        db.execute(
            "INSERT INTO main.documents VALUES (?, ?, ?, ?, ?)",
            (
                document.doc_id,
                document.case_id,
                document.kind,
                _iso(document.created_at),
                self._seal(payload, _ctx("documents", document.case_id, document.doc_id)),
            ),
        )
        ids: list[tuple[str, str | None]] = []
        for ordinal, text in enumerate(chunks):
            chunk_id = f"{document.doc_id}#{ordinal}"
            db.execute(
                "INSERT INTO main.chunks VALUES (?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    document.doc_id,
                    document.case_id,
                    document.kind,
                    ordinal,
                    self._seal(text.encode(), _ctx("chunks", document.case_id, chunk_id)),
                ),
            )
            ids.append((chunk_id, document.case_id))
        self._insert_vectors(db, ids, vectors)
        if document.case_id is not None:
            self._audit(db, AuditAction.DOCUMENT_ADDED, document.case_id)

    def _delete_documents(
        self, db: sqlite3.Connection, doc_ids: Sequence[str]
    ) -> tuple[int, int, int]:
        """Delete these documents with their chunks and vectors; return the three counts."""
        chunks = vectors = 0
        for doc_id in doc_ids:
            vectors += db.execute(
                "DELETE FROM idx.vectors WHERE chunk_id IN "
                "(SELECT chunk_id FROM main.chunks WHERE doc_id = ?)",
                (doc_id,),
            ).rowcount
            chunks += db.execute("DELETE FROM main.chunks WHERE doc_id = ?", (doc_id,)).rowcount
            db.execute("DELETE FROM main.documents WHERE doc_id = ?", (doc_id,))
        return len(doc_ids), chunks, vectors

    def documents(self, case_id: str | None = None) -> list[Document]:
        """Return the documents of ``case_id`` (user scope) or every document (global scope)."""
        self._require_case_filter(case_id)
        with self._lock:
            rows = self._db.execute(
                "SELECT doc_id, case_id, kind, created_at, body FROM main.documents "
                "WHERE case_id IS ? ORDER BY doc_id",
                (case_id,),
            ).fetchall()
        documents = []
        for doc_id, owner, kind, created_at, body in rows:
            payload = json.loads(self._unseal(body, _ctx("documents", owner, doc_id)))
            documents.append(
                Document(
                    doc_id=doc_id,
                    scope=self.scope,
                    case_id=owner,
                    kind=kind,
                    created_at=datetime.fromisoformat(created_at),
                    **payload,
                )
            )
        return documents

    def chunks(self, chunk_ids: Sequence[str], case_id: str | None = None) -> list[Chunk]:
        """Return the named chunks; in the user scope only those of ``case_id`` (BR-5)."""
        self._require_case_filter(case_id)
        wanted = list(dict.fromkeys(chunk_ids))
        marks = ",".join("?" * len(wanted))
        with self._lock:
            rows = self._db.execute(
                "SELECT chunk_id, doc_id, case_id, kind, ordinal, body FROM main.chunks "  # noqa: S608
                f"WHERE case_id IS ? AND chunk_id IN ({marks})",
                (case_id, *wanted),
            ).fetchall()
        found = {
            chunk_id: Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                scope=self.scope,
                case_id=owner,
                kind=kind,
                ordinal=ordinal,
                text=self._unseal(body, _ctx("chunks", owner, chunk_id)).decode(),
            )
            for chunk_id, doc_id, owner, kind, ordinal, body in rows
        }
        return [found[i] for i in wanted if i in found]

    # --- cases (user scope) -----------------------------------------------------------------

    def _audit(self, db: sqlite3.Connection, action: AuditAction, case_id: str) -> None:
        db.execute(
            "INSERT INTO main.audit_log (at, action, case_id, profile) VALUES (?, ?, ?, ?)",
            (_iso(utc_now()), action.value, case_id, self.profile),
        )

    def _case_row(self, db: sqlite3.Connection, case_id: str) -> CaseRecord:
        if self.scope is not CorpusScope.USER:
            raise CorpusError("cases live in the user scope")
        row = db.execute(
            "SELECT case_id, opened_at, closed_at, purged_at FROM main.cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise CaseNotFoundError
        return CaseRecord(
            case_id=row[0],
            opened_at=datetime.fromisoformat(row[1]),
            closed_at=None if row[2] is None else datetime.fromisoformat(row[2]),
            purged_at=None if row[3] is None else datetime.fromisoformat(row[3]),
        )

    def create_case(self, case_id: str, *, at: datetime | None = None) -> CaseRecord:
        """Create an open case (audited ``case_created``)."""
        record = CaseRecord(case_id=case_id, opened_at=at or utc_now())
        if self.scope is not CorpusScope.USER:
            raise CorpusError("cases live in the user scope")
        with self._tx() as db:
            try:
                db.execute(
                    "INSERT INTO main.cases (case_id, opened_at) VALUES (?, ?)",
                    (case_id, _iso(record.opened_at)),
                )
            except sqlite3.IntegrityError as exc:
                raise CorpusError("case exists") from exc
            self._audit(db, AuditAction.CASE_CREATED, case_id)
        return record

    def case_record(self, case_id: str) -> CaseRecord:
        """Return the case's lifecycle dates without auditing an access (no content is read).

        Raises:
            CaseNotFoundError: No such case.
        """
        with self._lock:
            return self._case_row(self._db, case_id)

    def open_case(self, case_id: str) -> CaseRecord:
        """Return the case record; every call appends a ``case_opened`` audit entry (US-4.6).

        Raises:
            CaseNotFoundError: No such case.
        """
        with self._tx() as db:
            record = self._case_row(db, case_id)
            self._audit(db, AuditAction.CASE_OPENED, case_id)
        return record

    def close_case(self, case_id: str, *, at: datetime | None = None) -> CaseRecord:
        """Close the case, which starts its retention clock (audited ``case_closed``).

        Raises:
            CaseNotFoundError: No such case.
        """
        closed_at = _iso(at or utc_now())
        with self._tx() as db:
            self._case_row(db, case_id)
            db.execute(
                # The first close starts the retention clock; closing again does not restart it.
                "UPDATE main.cases SET closed_at = COALESCE(closed_at, ?) WHERE case_id = ?",
                (closed_at, case_id),
            )
            self._audit(db, AuditAction.CASE_CLOSED, case_id)
            return self._case_row(db, case_id)

    def record_outcome(
        self, case_id: str, outcome: CaseOutcome, *, at: datetime | None = None
    ) -> OutcomeRecord:
        """Store the case's outcome: an enum and a date, nothing free-text (BR-7).

        Raises:
            CaseNotFoundError: No such case.
        """
        record = OutcomeRecord(case_id=case_id, outcome=outcome, recorded_at=at or utc_now())
        with self._tx() as db:
            self._case_row(db, case_id)
            db.execute(
                "INSERT OR REPLACE INTO main.outcomes VALUES (?, ?, ?)",
                (case_id, outcome.value, _iso(record.recorded_at)),
            )
            self._audit(db, AuditAction.OUTCOME_RECORDED, case_id)
        return record

    def outcome(self, case_id: str) -> OutcomeRecord | None:
        """Return the case's outcome, if one was recorded."""
        with self._lock:
            row = self._db.execute(
                "SELECT outcome, recorded_at FROM main.outcomes WHERE case_id = ?", (case_id,)
            ).fetchone()
        if row is None:
            return None
        return OutcomeRecord(
            case_id=case_id,
            outcome=CaseOutcome(row[0]),
            recorded_at=datetime.fromisoformat(row[1]),
        )

    # --- case items (user scope, US-5.1) ----------------------------------------------------

    def put_case_item(
        self, item: CaseItem, data: bytes | None = None, *, audit: AuditAction
    ) -> CaseItem:
        """Store (or replace) one item of an open case, sealed, with an audit entry.

        Args:
            item: The item; ``created_at`` is kept from the first store when it is replaced.
            data: Its bytes, if any (an attached file).
            audit: The audit action to record.

        Returns:
            The item as stored.

        Raises:
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        case_id, item_id = item.case_id, item.item_id
        context = _ctx("case_items", case_id, item_id)
        with self._tx() as db:
            record = self._case_row(db, case_id)
            if record.closed_at is not None or record.purged_at is not None:
                raise CaseClosedError
            row = db.execute(
                "SELECT created_at FROM main.case_items WHERE case_id = ? AND item_id = ?",
                (case_id, item_id),
            ).fetchone()
            if row is not None:
                item = item.model_copy(update={"created_at": datetime.fromisoformat(row[0])})
            db.execute(
                "INSERT OR REPLACE INTO main.case_items VALUES (?, ?, ?, ?, ?, ?)",
                (
                    case_id,
                    item_id,
                    item.kind,
                    _iso(item.created_at),
                    self._seal(item.payload, f"{context}:payload"),
                    None if data is None else self._seal(data, f"{context}:data"),
                ),
            )
            self._audit(db, audit, case_id)
        return item

    def case_items(self, case_id: str, kind: CaseItemKind) -> list[CaseItem]:
        """Return the case's items of ``kind``, oldest first, without their bytes."""
        with self._lock:
            self._case_row(self._db, case_id)
            rows = self._db.execute(
                "SELECT item_id, created_at, payload FROM main.case_items "
                "WHERE case_id = ? AND kind = ? ORDER BY created_at, item_id",
                (case_id, kind),
            ).fetchall()
        return [
            CaseItem(
                case_id=case_id,
                item_id=item_id,
                kind=kind,
                created_at=datetime.fromisoformat(created_at),
                payload=self._unseal(payload, f"{_ctx('case_items', case_id, item_id)}:payload"),
            )
            for item_id, created_at, payload in rows
        ]

    def case_item_data(self, case_id: str, item_id: str) -> bytes | None:
        """Return an item's bytes; ``None`` when it has none or does not exist."""
        with self._lock:
            row = self._db.execute(
                "SELECT data FROM main.case_items WHERE case_id = ? AND item_id = ?",
                (case_id, item_id),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return self._unseal(row[0], f"{_ctx('case_items', case_id, item_id)}:data")

    def expired_cases(self, cutoff: datetime) -> list[str]:
        """Return the cases closed at or before ``cutoff`` that still hold content (US-4.5).

        Lifecycle dates only; this is not a case access and is not audited.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT case_id FROM main.cases WHERE closed_at IS NOT NULL AND closed_at <= ? "
                "AND (EXISTS (SELECT 1 FROM main.documents d WHERE d.case_id = cases.case_id) "
                "OR EXISTS (SELECT 1 FROM main.case_items i WHERE i.case_id = cases.case_id)) "
                "ORDER BY case_id",
                (_iso(cutoff),),
            ).fetchall()
        return [row[0] for row in rows]

    def purge_case_content(
        self,
        case_id: str,
        *,
        at: datetime | None = None,
        reason: Literal["retention", "request"] = "retention",
    ) -> tuple[int, int, int]:
        """Delete the case's documents with their chunks and vectors, and its items (audited).

        The case row, its outcome, and its audit entries remain. Both WAL files are truncated
        afterwards so no deleted page image stays on disk; a checkpoint that a concurrent reader
        blocks is logged and repeated by the next purge.

        Args:
            case_id: The case.
            at: When it happened; now by default.
            reason: The retention policy (``case_purged``) or an approved request
                (``case_purged_on_request``).

        Returns:
            ``(documents, chunks, vectors)`` deleted; attached source files count as documents.

        Raises:
            CaseNotFoundError: No such case.
        """
        with self._tx() as db:
            self._case_row(db, case_id)
            doc_ids = db.execute("SELECT doc_id FROM main.documents WHERE case_id = ?", (case_id,))
            documents, chunks, vectors = self._delete_documents(db, [row[0] for row in doc_ids])
            (sources,) = db.execute(
                "SELECT count(*) FROM main.case_items WHERE case_id = ? AND kind = 'source'",
                (case_id,),
            ).fetchone()
            db.execute("DELETE FROM main.case_items WHERE case_id = ?", (case_id,))
            db.execute(
                "UPDATE main.cases SET purged_at = ? WHERE case_id = ?",
                (_iso(at or utc_now()), case_id),
            )
            by_policy = reason == "retention"
            purged = AuditAction.CASE_PURGED if by_policy else AuditAction.CASE_PURGED_ON_REQUEST
            self._audit(db, purged, case_id)
        self.checkpoint()
        return documents + sources, chunks, vectors

    def checkpoint(self) -> bool:
        """Truncate both WAL files; return ``False`` (and log) when a reader blocked it."""
        with self._lock:
            busy = [
                self._db.execute(f"PRAGMA {schema}.wal_checkpoint(TRUNCATE)").fetchone()[0]
                for schema in ("main", "idx")
            ]
        if any(busy):
            _log.warning("a WAL checkpoint was blocked by a reader; the next purge retries it")
        return not any(busy)

    def audit_log(self, case_id: str | None = None) -> list[AuditEntry]:
        """Return the audit entries, oldest first; only ``case_id``'s when given."""
        query = "SELECT seq, at, action, case_id, profile FROM main.audit_log"
        with self._lock:
            if case_id is None:
                rows = self._db.execute(f"{query} ORDER BY seq").fetchall()
            else:
                rows = self._db.execute(
                    f"{query} WHERE case_id = ? ORDER BY seq", (case_id,)
                ).fetchall()
        return [
            AuditEntry(
                seq=seq,
                at=datetime.fromisoformat(at),
                action=AuditAction(action),
                case_id=owner,
                profile=profile,
            )
            for seq, at, action, owner, profile in rows
        ]

    # --- status -----------------------------------------------------------------------------

    def status(self) -> ScopeStatus:
        """Return counts and index information; no content."""
        with self._lock:
            counts = [
                self._db.execute(f"SELECT count(*) FROM main.{table}").fetchone()[0]  # noqa: S608
                for table in ("cases", "documents", "chunks")
            ]
        return ScopeStatus(
            scope=self.scope,
            profile=self.profile,
            path=str(self.directory),
            encrypted=self._cipher is not None,
            cases=counts[0],
            documents=counts[1],
            chunks=counts[2],
            index=self.index_info(),
        )
