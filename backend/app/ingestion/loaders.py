"""Turn a file on disk into raw text (or, for PDFs, per-page text) ready for
the chunkers in chunking.py. No chunking logic lives here — this module's
only job is "read the bytes, decode them into text."
"""

from pathlib import Path
from typing import List, Tuple


def load_text_file(path: Path) -> str:
    """Shared by .md and .txt — both are just UTF-8 text on disk.
    `errors="replace"` avoids a hard crash on a stray non-UTF-8 byte in a
    student's notes file; it's better to ingest with a replacement character
    than to fail the whole file.
    """
    return path.read_text(encoding="utf-8", errors="replace")


def load_markdown_file(path: Path) -> str:
    return load_text_file(path)


def load_pdf_file(path: Path) -> List[Tuple[int, str]]:
    """Extract text page by page. Returns 1-indexed (page_number, text)
    pairs so page numbers in citations match what a human would see when
    opening the PDF.

    Import is local to this function so that importing `loaders` doesn't
    require pypdf unless a PDF is actually being loaded.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: List[Tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((i, text))
    return pages
