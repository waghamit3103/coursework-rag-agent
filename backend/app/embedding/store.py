"""Persistent vector storage for embedded chunks, backed by ChromaDB.

Design decision — single collection, metadata-filtered, not one collection
per course:
A separate ChromaDB collection per course would also work, but a single
collection with `course` (and `topic`) as metadata fields is simpler: one
persistence path, one place to reason about the schema, and course
filtering is just a `where` clause away — which is exactly the shape the
agent's `search_notes(query, course_filter?)` tool needs in Stage 4 (an
*optional* filter over an otherwise-shared search space, not a hard
partition the agent has to pick between up front).

Design decision — delete-then-insert per source file, not ID-based upsert
alone:
Chunk IDs are deterministic (see ingestion.models.chunk_id), so a plain
upsert would correctly overwrite chunks that still exist after re-chunking
a file. But if a file's content changes such that it now produces *fewer*
chunks than before (say 5 instead of 7), an upsert alone leaves the old
chunk_index 5 and 6 behind as orphaned, stale entries — nothing would ever
overwrite or remove them. Clearing every existing chunk for a source file
before inserting its fresh set sidesteps that entirely: the store always
reflects exactly the current chunking of a file, with no diffing logic
required.
"""

from pathlib import Path
from typing import List, Optional

import chromadb

from app import config
from app.ingestion.models import Chunk, chunk_id


class NotesStore:
    def __init__(
        self,
        persist_dir: Path = config.CHROMA_PERSIST_DIR,
        collection_name: str = config.CHROMA_COLLECTION_NAME,
    ):
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(collection_name)

    def upsert_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Got {len(chunks)} chunks but {len(embeddings)} embeddings — "
                "these must be the same length and in the same order."
            )
        if not chunks:
            return

        self._collection.upsert(
            ids=[chunk_id(c) for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata.to_chroma_metadata() for c in chunks],
            documents=[c.text for c in chunks],
        )

    def delete_by_source_file(self, course: str, topic: str, source_file: str) -> None:
        """No-op (not an error) if nothing matches — this is called
        unconditionally before every re-embed of a file, including the
        first time a file is ever ingested.
        """
        self._collection.delete(
            where={
                "$and": [
                    {"course": course},
                    {"topic": topic},
                    {"source_file": source_file},
                ]
            }
        )

    def count(self) -> int:
        return self._collection.count()

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> dict:
        """Raw ChromaDB query — returns the native Chroma result dict
        (ids/documents/metadatas/distances, each a list-of-lists keyed by
        query). Stage 3 builds the retrieve(query, course_filter) function
        that wraps this into a clean, agent-tool-friendly result shape;
        this method stays a thin pass-through so the storage layer doesn't
        need to know about that shape.
        """
        return self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
        )
