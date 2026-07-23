import json
import shutil
from pathlib import Path

import pytest

from app.ingestion.pipeline import (
    chunk_file,
    course_topic_from_path,
    discover_source_files,
    ingest_all,
    write_chunks_jsonl,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def notes_root(tmp_path: Path) -> Path:
    """Build a root/<course>/<topic>/<file> tree from the test fixtures,
    mirroring the real data/raw_notes/ layout.
    """
    root = tmp_path / "raw_notes"

    dsa_dir = root / "dsa" / "trees"
    dsa_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "sample.md", dsa_dir / "bst.md")

    os_dir = root / "operating_systems" / "scheduling"
    os_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "sample_flat.txt", os_dir / "scheduling.txt")
    shutil.copy(FIXTURES / "sample.pdf", os_dir / "scheduling.pdf")

    # A file that should be ignored (unsupported extension).
    (os_dir / "notes.png").write_bytes(b"not a real image, just testing extension filtering")

    return root


def test_discover_source_files_finds_supported_and_ignores_others(notes_root: Path):
    found = discover_source_files(notes_root)
    names = {p.name for p in found}
    assert names == {"bst.md", "scheduling.txt", "scheduling.pdf"}


def test_course_topic_from_path(notes_root: Path):
    path = notes_root / "dsa" / "trees" / "bst.md"
    assert course_topic_from_path(path, notes_root) == ("dsa", "trees")


def test_course_topic_from_path_rejects_shallow_paths(tmp_path: Path):
    root = tmp_path / "raw_notes"
    root.mkdir()
    misplaced = root / "loose_file.md"
    misplaced.write_text("x")
    with pytest.raises(ValueError):
        course_topic_from_path(misplaced, root)


def test_chunk_file_markdown_has_correct_metadata(notes_root: Path):
    path = notes_root / "dsa" / "trees" / "bst.md"
    chunks = chunk_file(path, notes_root)

    assert len(chunks) > 1
    first = chunks[0]
    assert first.metadata.course == "dsa"
    assert first.metadata.topic == "trees"
    assert first.metadata.source_file == "bst.md"
    assert first.metadata.chunking_method == "heading"
    assert first.metadata.section == "Binary Search Trees"
    assert first.metadata.page is None

    # chunk_index is contiguous starting at 0
    assert [c.metadata.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_file_text_uses_fixed_size_with_no_section(notes_root: Path):
    path = notes_root / "operating_systems" / "scheduling" / "scheduling.txt"
    chunks = chunk_file(path, notes_root)

    assert len(chunks) >= 1
    for c in chunks:
        assert c.metadata.chunking_method == "fixed_size"
        assert c.metadata.section is None
        assert c.metadata.page is None
        assert c.metadata.course == "operating_systems"
        assert c.metadata.topic == "scheduling"


def test_chunk_file_pdf_records_page_numbers(notes_root: Path):
    path = notes_root / "operating_systems" / "scheduling" / "scheduling.pdf"
    chunks = chunk_file(path, notes_root)

    assert len(chunks) >= 2
    pages = {c.metadata.page for c in chunks}
    assert pages == {1, 2}
    for c in chunks:
        assert c.metadata.source_file == "scheduling.pdf"


def test_ingest_all_covers_every_discovered_file(notes_root: Path):
    chunks = ingest_all(notes_root)
    source_files = {c.metadata.source_file for c in chunks}
    assert source_files == {"bst.md", "scheduling.txt", "scheduling.pdf"}


def test_write_chunks_jsonl_round_trips(notes_root: Path, tmp_path: Path):
    chunks = ingest_all(notes_root)
    out_path = tmp_path / "processed" / "chunks.jsonl"
    write_chunks_jsonl(chunks, out_path)

    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(chunks)

    first_record = json.loads(lines[0])
    assert "text" in first_record
    assert "metadata" in first_record
    assert "course" in first_record["metadata"]
