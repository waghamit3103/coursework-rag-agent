#!/usr/bin/env python
"""CLI entry point: chunk everything under data/raw_notes/ and write
data/processed/chunks.jsonl.

Usage (from backend/, with venv activated):
    python scripts/run_ingestion.py
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.ingestion.pipeline import ingest_all, write_chunks_jsonl


def main() -> None:
    if not config.RAW_NOTES_DIR.exists():
        print(f"No raw notes directory found at {config.RAW_NOTES_DIR}")
        return

    chunks = ingest_all(config.RAW_NOTES_DIR)
    write_chunks_jsonl(chunks, config.CHUNKS_JSONL_PATH)

    print(f"Ingested {len(chunks)} chunks -> {config.CHUNKS_JSONL_PATH}")

    by_course = Counter(c.metadata.course for c in chunks)
    for course, n in sorted(by_course.items()):
        print(f"  {course}: {n} chunks")

    by_method = Counter(c.metadata.chunking_method for c in chunks)
    if chunks:
        print("Chunking methods used:")
        for method, n in sorted(by_method.items()):
            print(f"  {method}: {n}")


if __name__ == "__main__":
    main()
