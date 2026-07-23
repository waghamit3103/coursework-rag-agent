"""Chunking strategy: heading-aware where structure exists, fixed-size with
overlap where it doesn't.

Design decision — word-based sizing, not token-based:
Chunk boundaries are measured in whitespace-split words, not LLM tokens. A
precise token count would require calling a tokenizer (and Claude's
tokenizer isn't a local, dependency-free library — the Claude API's own
`count_tokens` endpoint is a network call). Word count is a stable, free,
deterministic proxy that's standard practice for chunking pipelines: it
doesn't need to match the embedding model's or the LLM's tokenizer, it only
needs to produce chunks of roughly consistent, retrieval-friendly size.
~300 words is roughly 400-450 tokens for typical English prose — a
reasonable single "concept" per chunk for Voyage's embedding context.

Design decision — heading stack, not a full document tree:
`split_markdown_into_sections` tracks a simple stack of currently-open
headings by level. It does not build a nested tree of Section objects with
children. Course notes almost always use headings in-order without
weird skips (h1 -> h3 with no h2), so a stack is sufficient and much simpler
to reason about and test than a tree. If heading levels are skipped, the
resulting path just reflects whatever real headings were seen — it doesn't
error, it just produces a slightly shorter path, which is an acceptable
degradation for this input domain.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```|~~~)")

# One chunk result: (text, section_label_or_None, method)
ChunkResult = Tuple[str, Optional[str], str]


@dataclass
class Section:
    heading_path: List[str]
    content: str


def split_markdown_into_sections(text: str) -> List[Section]:
    """Split text into sections at ATX (`#`) heading boundaries.

    Headings inside fenced code blocks (``` or ~~~) are not treated as
    headings — a `# comment` inside a Python snippet shouldn't split the
    document. Content that precedes the first heading (or a document with
    no headings at all) becomes a section with an empty heading_path, so it
    still produces a chunk rather than being silently dropped.
    """
    lines = text.splitlines()
    sections: List[Section] = []
    heading_stack: List[str] = []
    current_lines: List[str] = []
    in_fence = False

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(Section(heading_path=list(heading_stack), content=content))

    for line in lines:
        if _FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            current_lines.append(line)
            continue

        if not in_fence:
            match = _ATX_HEADING_RE.match(line)
            if match:
                flush()
                current_lines = []
                level = len(match.group(1))
                title = match.group(2).strip()
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                continue

        current_lines.append(line)

    flush()
    return sections


def fixed_size_chunks(
    text: str,
    chunk_size_words: int,
    overlap_words: int,
    min_chunk_words: int,
) -> List[str]:
    """Sliding-window word chunker with overlap.

    A trailing window smaller than `min_chunk_words` is merged into the
    previous chunk rather than emitted as its own tiny, low-signal chunk.
    """
    if overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be smaller than chunk_size_words")

    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size_words:
        return [" ".join(words)]

    step = chunk_size_words - overlap_words
    chunks: List[str] = []
    start = 0
    n = len(words)

    while start < n:
        end = min(start + chunk_size_words, n)
        window = words[start:end]

        if chunks and end == n and len(window) < min_chunk_words:
            chunks[-1] = chunks[-1] + " " + " ".join(window)
            break

        chunks.append(" ".join(window))

        if end == n:
            break
        start += step

    return chunks


def chunk_markdown(
    text: str,
    chunk_size_words: int,
    overlap_words: int,
    max_section_words: int,
    min_chunk_words: int,
) -> List[ChunkResult]:
    """Heading-aware chunking, falling back to fixed-size per oversized
    section.

    Every section keeps its heading path as metadata even when it must be
    sub-chunked — so a citation always points at the right subsection, not
    just "somewhere in this large section."
    """
    sections = split_markdown_into_sections(text)
    results: List[ChunkResult] = []

    for section in sections:
        label = " > ".join(p for p in section.heading_path if p) or None
        word_count = len(section.content.split())

        if word_count <= max_section_words:
            results.append((section.content, label, "heading"))
        else:
            for sub_chunk in fixed_size_chunks(
                section.content, chunk_size_words, overlap_words, min_chunk_words
            ):
                results.append((sub_chunk, label, "heading+fixed_size"))

    return results
