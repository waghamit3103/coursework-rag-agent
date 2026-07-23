#!/usr/bin/env python
"""CLI entry point: embed data/processed/chunks.jsonl (produced by
scripts/run_ingestion.py) and persist to ChromaDB at data/chroma/.

Usage (from backend/, with venv activated, VOYAGE_API_KEY set in .env):
    python scripts/run_ingestion.py   # if you haven't already
    python scripts/run_embedding.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.embedding.pipeline import embed_and_store
from app.embedding.store import NotesStore
from app.embedding.voyage_client import build_default_embedder
from app.ingestion.pipeline import read_chunks_jsonl


def main() -> None:
    if not config.CHUNKS_JSONL_PATH.exists():
        print(
            f"No chunks found at {config.CHUNKS_JSONL_PATH}. "
            "Run scripts/run_ingestion.py first."
        )
        return

    chunks = read_chunks_jsonl(config.CHUNKS_JSONL_PATH)
    print(f"Loaded {len(chunks)} chunks from {config.CHUNKS_JSONL_PATH}")

    embedder = build_default_embedder()
    store = NotesStore()

    stats = embed_and_store(chunks, embedder, store)

    print(
        f"Embedded {stats.chunks_embedded} chunks across {stats.files_processed} "
        f"file(s) ({stats.total_tokens} Voyage tokens used)."
    )
    print(f"ChromaDB collection now has {store.count()} chunks total.")
    print(f"Persisted at {config.CHROMA_PERSIST_DIR}")


if __name__ == "__main__":
    main()
