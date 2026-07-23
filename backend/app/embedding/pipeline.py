"""Orchestrates Stage 2: given chunks (from Stage 1) plus a VoyageEmbedder
and a NotesStore, embed and persist them.

Design decision — batch the Voyage API call across the *whole* corpus, not
one call per source file:
An earlier version of this pipeline called embed_documents() once per
source file, alongside delete_by_source_file() (see store.py's docstring
for why deletion is per-file). That turned out to be a real mistake, not
just a theoretical one: running it against a freshly created Voyage AI
account (no payment method on file yet, so subject to Voyage's reduced
rate limit of 3 requests/minute) immediately hit RateLimitError, because 6
sample files meant 6 back-to-back API calls. Grouping by file conflates
two unrelated concerns — "which local DB rows are stale and need
replacing" (must be scoped per file) and "how should API calls be batched"
(should be batched by Voyage's request-size limit across *all* pending
text, unrelated to file boundaries) — and conflating them meant paying a
full network round trip (and a full rate-limit slot) per file instead of
per VOYAGE_EMBED_BATCH_SIZE texts. Splitting them means this pipeline now
issues exactly ceil(total_chunks / batch_size) Voyage API calls per run
regardless of how many files those chunks came from — 1 call for our
32-chunk sample set, not 6.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import List, Tuple

from app.embedding.store import NotesStore
from app.embedding.voyage_client import VoyageEmbedder
from app.ingestion.models import Chunk


@dataclass
class EmbeddingRunStats:
    files_processed: int
    chunks_embedded: int
    total_tokens: int


def _group_by_source_file(chunks: List[Chunk]) -> dict:
    groups: dict = defaultdict(list)
    for chunk in chunks:
        key: Tuple[str, str, str] = (
            chunk.metadata.course,
            chunk.metadata.topic,
            chunk.metadata.source_file,
        )
        groups[key].append(chunk)
    return groups


def embed_and_store(
    chunks: List[Chunk], embedder: VoyageEmbedder, store: NotesStore
) -> EmbeddingRunStats:
    groups = _group_by_source_file(chunks)

    # Clear stale rows for every file up front. These are local ChromaDB
    # operations — no Voyage API calls, no rate-limit exposure — so doing
    # all of them before any embedding call means a failed embed never
    # leaves the store in a mixed stale-plus-partial-new state.
    for course, topic, source_file in groups:
        store.delete_by_source_file(course, topic, source_file)

    texts = [c.text for c in chunks]
    result = embedder.embed_documents(texts)
    store.upsert_chunks(chunks, result.embeddings)

    return EmbeddingRunStats(
        files_processed=len(groups),
        chunks_embedded=len(chunks),
        total_tokens=result.total_tokens,
    )
