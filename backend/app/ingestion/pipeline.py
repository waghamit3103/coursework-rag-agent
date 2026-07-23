"""Ties loaders + chunkers together: walk data/raw_notes/<course>/<topic>/,
produce Chunk objects with full metadata, and write them out for the next
stage (embedding) to pick up.

The course/topic taxonomy comes from the directory structure itself
(root/<course>/<topic>/<file>) rather than from front-matter or a config
file — one less thing to keep in sync, and it matches how the user already
organizes notes on disk.
"""

import json
from pathlib import Path
from typing import List, Tuple

from app import config
from app.ingestion.chunking import chunk_markdown, fixed_size_chunks
from app.ingestion.loaders import load_markdown_file, load_pdf_file, load_text_file
from app.ingestion.models import Chunk, ChunkMetadata


def discover_source_files(root: Path) -> List[Path]:
    """Find every supported file under root, sorted for deterministic
    ordering (important for reproducible tests and stable chunk_index
    values across re-ingestion runs).
    """
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in config.SUPPORTED_EXTENSIONS
    )


def course_topic_from_path(path: Path, root: Path) -> Tuple[str, str]:
    """Derive (course, topic) from a file's position under root.

    Raises ValueError rather than guessing if a file sits directly in root
    or in only one subdirectory — that's a misplaced file, not a valid
    course/topic pair, and failing loudly beats silently mis-tagging it.
    """
    rel_parts = path.relative_to(root).parts
    if len(rel_parts) < 3:
        raise ValueError(
            f"Expected data/raw_notes/<course>/<topic>/<file>, got: "
            f"{path.relative_to(root)}"
        )
    return rel_parts[0], rel_parts[1]


def chunk_file(path: Path, root: Path) -> List[Chunk]:
    course, topic = course_topic_from_path(path, root)
    ext = path.suffix.lower()

    if ext == ".md":
        return _chunk_markdown_file(path, course, topic)
    if ext == ".txt":
        return _chunk_text_file(path, course, topic)
    if ext == ".pdf":
        return _chunk_pdf_file(path, course, topic)
    raise ValueError(f"Unsupported file extension: {ext}")


def _chunk_markdown_file(path: Path, course: str, topic: str) -> List[Chunk]:
    text = load_markdown_file(path)
    results = chunk_markdown(
        text,
        config.CHUNK_SIZE_WORDS,
        config.CHUNK_OVERLAP_WORDS,
        config.MAX_SECTION_WORDS,
        config.MIN_CHUNK_WORDS,
    )
    return [
        Chunk(
            text=chunk_text,
            metadata=ChunkMetadata(
                course=course,
                topic=topic,
                source_file=path.name,
                chunk_index=idx,
                chunking_method=method,
                section=section,
            ),
        )
        for idx, (chunk_text, section, method) in enumerate(results)
    ]


def _chunk_text_file(path: Path, course: str, topic: str) -> List[Chunk]:
    text = load_text_file(path)
    chunks = fixed_size_chunks(
        text, config.CHUNK_SIZE_WORDS, config.CHUNK_OVERLAP_WORDS, config.MIN_CHUNK_WORDS
    )
    return [
        Chunk(
            text=chunk_text,
            metadata=ChunkMetadata(
                course=course,
                topic=topic,
                source_file=path.name,
                chunk_index=idx,
                chunking_method="fixed_size",
                section=None,
            ),
        )
        for idx, chunk_text in enumerate(chunks)
    ]


def _chunk_pdf_file(path: Path, course: str, topic: str) -> List[Chunk]:
    """PDFs are chunked per page: each page is run through the same
    heading-detection logic as markdown (some course PDFs are exports of
    already-structured notes and do contain real ATX-style headings), and
    falls back to fixed-size chunking per page otherwise. The page number
    is always recorded, regardless of which method chunked that page.
    """
    chunks: List[Chunk] = []
    idx = 0

    for page_num, page_text in load_pdf_file(path):
        if not page_text.strip():
            continue

        results = chunk_markdown(
            page_text,
            config.CHUNK_SIZE_WORDS,
            config.CHUNK_OVERLAP_WORDS,
            config.MAX_SECTION_WORDS,
            config.MIN_CHUNK_WORDS,
        )
        has_real_headings = any(section for _, section, _ in results)

        if has_real_headings:
            for chunk_text, section, method in results:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        metadata=ChunkMetadata(
                            course=course,
                            topic=topic,
                            source_file=path.name,
                            chunk_index=idx,
                            chunking_method=method,
                            section=section,
                            page=page_num,
                        ),
                    )
                )
                idx += 1
        else:
            for chunk_text in fixed_size_chunks(
                page_text,
                config.CHUNK_SIZE_WORDS,
                config.CHUNK_OVERLAP_WORDS,
                config.MIN_CHUNK_WORDS,
            ):
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        metadata=ChunkMetadata(
                            course=course,
                            topic=topic,
                            source_file=path.name,
                            chunk_index=idx,
                            chunking_method="fixed_size",
                            section=None,
                            page=page_num,
                        ),
                    )
                )
                idx += 1

    return chunks


def ingest_all(root: Path) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    for path in discover_source_files(root):
        all_chunks.extend(chunk_file(path, root))
    return all_chunks


def write_chunks_jsonl(chunks: List[Chunk], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")


def read_chunks_jsonl(path: Path) -> List[Chunk]:
    """Inverse of write_chunks_jsonl — lets the embedding stage consume the
    ingestion stage's output without needing to re-run chunking, so the two
    stages stay independently runnable and testable.
    """
    chunks: List[Chunk] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            chunks.append(
                Chunk(text=record["text"], metadata=ChunkMetadata(**record["metadata"]))
            )
    return chunks
