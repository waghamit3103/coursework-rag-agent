"""Standalone retrieval: embed a query, search the vector store, return a
clean result — independent of and testable without the agent loop. Stage 4
wires this up as the `search_notes` tool; nothing here knows Claude exists.

Design decision — dependency-injected embedder/store, mirroring Stage 2:
`retrieve()` takes a VoyageEmbedder and NotesStore rather than constructing
its own, so tests can inject a scripted fake embedder and a real (but
tmp_path-local) ChromaDB store and get genuine ranking-correctness
assertions — not just "did this function run without crashing" — with zero
network calls. See tests/test_retriever.py.
"""

from dataclasses import dataclass
from typing import List, Optional

from app import config
from app.embedding.store import NotesStore
from app.embedding.voyage_client import VoyageEmbedder, build_default_embedder


@dataclass
class RetrievedChunk:
    text: str
    course: str
    topic: str
    source_file: str
    chunk_index: int
    chunking_method: str
    score: float  # cosine similarity: 1.0 = identical direction, higher = more relevant
    section: Optional[str] = None
    page: Optional[int] = None

    def citation(self) -> str:
        """Human-readable source pointer for rendering under an answer,
        e.g. "dsa/trees/binary_search_trees.md > Binary Search Trees >
        Insertion" or "oop/design_patterns/factory_pattern.pdf (page 2)".
        Section and page are independent fields on the dataclass (see
        ingestion.models.ChunkMetadata) precisely so a caller can format
        them differently if needed — this method is just the default.
        """
        location = f"{self.course}/{self.topic}/{self.source_file}"
        if self.section:
            location += f" > {self.section}"
        if self.page is not None:
            location += f" (page {self.page})"
        return location


def retrieve(
    query: str,
    embedder: VoyageEmbedder,
    store: NotesStore,
    course_filter: Optional[str] = None,
    n_results: int = config.DEFAULT_RETRIEVAL_N_RESULTS,
) -> List[RetrievedChunk]:
    """Embed `query` (input_type="query" — see VoyageEmbedder) and return
    the top `n_results` chunks, optionally restricted to one course.

    Returns an empty list, never raises, if nothing matches (empty store,
    or a course_filter with no chunks) — "no results" is a normal outcome
    the agent needs to reason about (re-query with different terms), not
    an error condition.
    """
    query_embedding = embedder.embed_query(query)
    where = {"course": course_filter} if course_filter else None

    raw = store.query(query_embedding, n_results=n_results, where=where)
    return _parse_chroma_result(raw)


def retrieve_with_defaults(
    query: str,
    course_filter: Optional[str] = None,
    n_results: int = config.DEFAULT_RETRIEVAL_N_RESULTS,
) -> List[RetrievedChunk]:
    """Convenience wrapper for scripts/manual querying — constructs the
    real Voyage embedder and the on-disk NotesStore. Application code
    (Stage 4's agent tool, Stage 5's API) should prefer constructing an
    embedder/store once and calling retrieve() directly, rather than
    paying embedder/store construction cost on every call.
    """
    embedder = build_default_embedder()
    store = NotesStore()
    return retrieve(query, embedder, store, course_filter, n_results)


def _parse_chroma_result(raw: dict) -> List[RetrievedChunk]:
    """Chroma's query() returns parallel lists-of-lists keyed by query
    (we only ever send one query embedding, so index [0] throughout).
    Cosine distance -> similarity: score = 1 - distance (see store.py's
    module docstring for why the collection is configured for cosine
    distance in the first place, and why that conversion is exact).
    """
    documents = raw["documents"][0]
    metadatas = raw["metadatas"][0]
    distances = raw["distances"][0]

    return [
        RetrievedChunk(
            text=text,
            course=metadata["course"],
            topic=metadata["topic"],
            source_file=metadata["source_file"],
            chunk_index=metadata["chunk_index"],
            chunking_method=metadata["chunking_method"],
            section=metadata.get("section"),
            page=metadata.get("page"),
            score=1.0 - distance,
        )
        for text, metadata, distance in zip(documents, metadatas, distances)
    ]
