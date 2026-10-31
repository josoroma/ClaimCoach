"""Import a corpus bundle into the global scope and list it with provenance.

Implements: US-4.3 (``import_bundle``: all-or-nothing, idempotent by ``kind:key``; ``corpus_view``
shows source, verified-on date, and the stale flag). Rules: BR-1 (the bundle is local; embeddings
run on the local ``embedding`` role), PRD §11.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from claimcoach.corpus.bundle import (
    CorpusBundle,
    CorpusItem,
    CorpusViewItem,
    CorpusViewResponse,
    ImportResult,
    is_stale,
)
from claimcoach.corpus.embed import Embedder
from claimcoach.corpus.errors import CorpusError, IndexStaleError
from claimcoach.corpus.store import CorpusStore, Vectors, split_text
from claimcoach.corpus.types import CorpusScope, Document

__all__ = ["corpus_view", "import_bundle", "item_document"]


def item_document(item: CorpusItem) -> Document:
    """Return the global-scope document an item is stored as (ID ``kind:key``)."""
    extra = item.model_dump(mode="json", exclude={"kind", "title", "body", "source", "verified_on"})
    metadata = {
        "key": item.key,
        "source": item.source,
        "verified_on": item.verified_on.isoformat(),
        **{name: str(value) for name, value in extra.items()},
    }
    return Document(
        doc_id=f"{item.kind}:{item.key}",
        scope=CorpusScope.GLOBAL,
        kind=item.kind,
        title=item.title,
        text=item.body,
        metadata=metadata,
    )


async def import_bundle(
    store: CorpusStore, bundle: CorpusBundle, embedder: Embedder
) -> ImportResult:
    """Embed every item, then store them all in one transaction.

    Each chunk is embedded with the item's title in front, so a passage keeps its context; the
    whole bundle goes to the model in one held session.

    Raises:
        CorpusError: ``store`` is not the global scope.
        IndexStaleError: The index needs a reindex first (checked before anything is embedded).
        ModelUnavailableError: The embedding model failed; nothing is stored.
    """
    if store.scope is not CorpusScope.GLOBAL:
        raise CorpusError("imports go to the global scope")
    if store.index_info().needs_reindex:
        raise IndexStaleError
    documents = [item_document(item) for item in bundle.items]
    pieces = [
        [f"{item.title}\n{piece}" for piece in split_text(item.body)] for item in bundle.items
    ]
    # One embedding call for the whole bundle: one hold on the model, full batches.
    vectors = await embedder.embed_documents([text for chunks in pieces for text in chunks])
    entries: list[tuple[Document, list[str], Vectors]] = []
    start = 0
    for document, chunks in zip(documents, pieces, strict=True):
        entries.append((document, chunks, vectors[start : start + len(chunks)]))
        start += len(chunks)
    chunks_stored = store.put_documents(entries)
    imported = Counter(item.kind for item in bundle.items)
    return ImportResult(imported=dict(sorted(imported.items())), chunks=chunks_stored)


def corpus_view(store: CorpusStore, today: date) -> CorpusViewResponse:
    """List every global item with its provenance and whether it is stale on ``today``."""
    items = []
    for document in store.documents():
        verified_on = date.fromisoformat(document.metadata["verified_on"])
        items.append(
            CorpusViewItem.model_validate(
                {
                    "kind": document.kind,
                    "key": document.metadata["key"],
                    "title": document.title,
                    "source": document.metadata["source"],
                    "verified_on": verified_on,
                    "stale": is_stale(verified_on, today),
                }
            )
        )
    return CorpusViewResponse(items=sorted(items, key=lambda item: (item.kind, item.key)))
