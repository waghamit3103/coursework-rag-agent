from pathlib import Path

import pytest

from app.agent.tools import build_search_notes_tool, execute_search_notes
from app.embedding.pipeline import embed_and_store
from app.embedding.store import NotesStore
from app.ingestion.models import Chunk, ChunkMetadata
from tests.conftest import make_embedder as _embedder
from tests.fakes import FakeVoyageClient


def _chunk(course, topic, source_file, chunk_index, text, section=None) -> Chunk:
    return Chunk(
        text=text,
        metadata=ChunkMetadata(
            course=course,
            topic=topic,
            source_file=source_file,
            chunk_index=chunk_index,
            chunking_method="heading",
            section=section,
        ),
    )


@pytest.fixture
def store(tmp_path: Path) -> NotesStore:
    return NotesStore(persist_dir=tmp_path / "chroma", collection_name="test_notes")


class TestBuildSearchNotesTool:
    def test_course_filter_enum_derived_from_store(self, store: NotesStore):
        chunks = [
            _chunk("dsa", "trees", "bst.md", 0, text="binary search tree"),
            _chunk("oop", "design_patterns", "factory.md", 0, text="factory pattern"),
        ]
        embed_and_store(chunks, _embedder(FakeVoyageClient()), store)

        tool = build_search_notes_tool(store)

        assert tool["name"] == "search_notes"
        assert set(tool["input_schema"]["properties"]["course_filter"]["enum"]) == {"dsa", "oop"}
        assert tool["input_schema"]["required"] == ["query"]

    def test_empty_store_produces_empty_enum_not_an_error(self, store: NotesStore):
        tool = build_search_notes_tool(store)
        assert tool["input_schema"]["properties"]["course_filter"]["enum"] == []


class TestExecuteSearchNotes:
    def test_formats_results_with_score_and_citation(self, store: NotesStore):
        chunk = _chunk(
            "dsa", "trees", "bst.md", 0, text="a binary search tree definition", section="Intro"
        )
        client = FakeVoyageClient()
        embed_and_store([chunk], _embedder(client), store)

        text, results = execute_search_notes({"query": "bst"}, _embedder(client), store)

        assert len(results) == 1
        assert "dsa/trees/bst.md > Intro" in text
        assert "a binary search tree definition" in text
        assert "score=" in text

    def test_no_matches_returns_helpful_message_not_empty_string(self, store: NotesStore):
        client = FakeVoyageClient()
        text, results = execute_search_notes({"query": "anything"}, _embedder(client), store)

        assert results == []
        assert "No matching passages" in text

    def test_passes_through_course_filter(self, store: NotesStore):
        chunks = [
            _chunk("dsa", "trees", "bst.md", 0, text="binary search tree"),
            _chunk("oop", "design_patterns", "factory.md", 0, text="factory pattern"),
        ]
        client = FakeVoyageClient()
        embed_and_store(chunks, _embedder(client), store)

        _, results = execute_search_notes(
            {"query": "pattern", "course_filter": "oop"}, _embedder(client), store
        )

        assert len(results) == 1
        assert results[0].course == "oop"
