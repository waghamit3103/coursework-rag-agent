from pathlib import Path

from app.ingestion.loaders import load_markdown_file, load_pdf_file, load_text_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_markdown_file_reads_utf8_text():
    text = load_markdown_file(FIXTURES / "sample.md")
    assert "Binary Search Trees" in text
    assert text.startswith("# Binary Search Trees")


def test_load_text_file_reads_plain_text():
    text = load_text_file(FIXTURES / "sample_flat.txt")
    assert "Process scheduling" in text


def test_load_pdf_file_returns_one_indexed_pages_with_text():
    pages = load_pdf_file(FIXTURES / "sample.pdf")
    assert len(pages) == 2

    page_numbers = [p for p, _ in pages]
    assert page_numbers == [1, 2]

    _, page1_text = pages[0]
    _, page2_text = pages[1]
    assert "Process Scheduling" in page1_text
    assert "Deadlocks" in page2_text
