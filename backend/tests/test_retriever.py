import math
from pathlib import Path

import pytest

from app.embedding.pipeline import embed_and_store
from app.embedding.store import NotesStore
from app.ingestion.models import Chunk, ChunkMetadata
import app.retrieval.retriever as retriever_module
from app.retrieval.retriever import RetrievedChunk, retrieve, retrieve_with_defaults
from tests.conftest import make_embedder as _embedder
from tests.fakes import FakeVoyageClient, ScriptedVoyageClient


def _chunk(course, topic, source_file, chunk_index, text, section=None, page=None) -> Chunk:
    return Chunk(
        text=text,
        metadata=ChunkMetadata(
            course=course,
            topic=topic,
            source_file=source_file,
            chunk_index=chunk_index,
            chunking_method="heading",
            section=section,
            page=page,
        ),
    )


@pytest.fixture
def store(tmp_path: Path) -> NotesStore:
    return NotesStore(persist_dir=tmp_path / "chroma", collection_name="test_notes")


class TestRetrieveWiring:
    def test_query_embedding_uses_query_input_type(self, store: NotesStore):
        chunk = _chunk("dsa", "trees", "bst.md", 0, text="a binary search tree stores sorted data")
        client = FakeVoyageClient()
        embed_and_store([chunk], _embedder(client), store)

        client.calls.clear()
        retrieve("what is a bst?", _embedder(client), store)

        assert len(client.calls) == 1
        assert client.calls[0]["input_type"] == "query"

    def test_returns_empty_list_for_empty_store(self, store: NotesStore):
        results = retrieve("anything", _embedder(FakeVoyageClient()), store)
        assert results == []

    def test_course_filter_restricts_results(self, store: NotesStore):
        chunks = [
            _chunk("dsa", "trees", "bst.md", 0, text="binary search tree insertion"),
            _chunk("operating_systems", "scheduling", "sched.md", 0, text="round robin scheduling"),
        ]
        client = FakeVoyageClient()
        embed_and_store(chunks, _embedder(client), store)

        results = retrieve("trees", _embedder(client), store, course_filter="dsa")

        assert len(results) == 1
        assert results[0].course == "dsa"

    def test_course_filter_matching_nothing_returns_empty(self, store: NotesStore):
        chunks = [_chunk("dsa", "trees", "bst.md", 0, text="binary search tree")]
        client = FakeVoyageClient()
        embed_and_store(chunks, _embedder(client), store)

        results = retrieve("anything", _embedder(client), store, course_filter="oop")

        assert results == []

    def test_n_results_limits_count(self, store: NotesStore):
        chunks = [_chunk("dsa", "trees", "bst.md", i, text=f"chunk number {i}") for i in range(5)]
        client = FakeVoyageClient()
        embed_and_store(chunks, _embedder(client), store)

        results = retrieve("chunk", _embedder(client), store, n_results=2)

        assert len(results) == 2

    def test_populates_all_metadata_fields(self, store: NotesStore):
        chunk = _chunk(
            "oop",
            "design_patterns",
            "factory.pdf",
            3,
            text="factory method pattern",
            section="Factory Method Pattern",
            page=2,
        )
        client = FakeVoyageClient()
        embed_and_store([chunk], _embedder(client), store)

        [result] = retrieve("factory pattern", _embedder(client), store)

        assert result.text == "factory method pattern"
        assert result.course == "oop"
        assert result.topic == "design_patterns"
        assert result.source_file == "factory.pdf"
        assert result.chunk_index == 3
        assert result.chunking_method == "heading"
        assert result.section == "Factory Method Pattern"
        assert result.page == 2

    def test_optional_fields_default_to_none_when_absent(self, store: NotesStore):
        chunk = _chunk("operating_systems", "deadlocks", "notes.txt", 0, text="deadlock conditions")
        client = FakeVoyageClient()
        embed_and_store([chunk], _embedder(client), store)

        [result] = retrieve("deadlock", _embedder(client), store)

        assert result.section is None
        assert result.page is None


class TestCitation:
    def _result(self, **overrides) -> RetrievedChunk:
        defaults = dict(
            text="x",
            course="dsa",
            topic="trees",
            source_file="bst.md",
            chunk_index=0,
            chunking_method="heading",
            score=0.9,
        )
        defaults.update(overrides)
        return RetrievedChunk(**defaults)

    def test_with_section_and_no_page(self):
        result = self._result(section="Insertion", page=None)
        assert result.citation() == "dsa/trees/bst.md > Insertion"

    def test_with_page_and_no_section(self):
        result = self._result(
            course="oop", topic="design_patterns", source_file="factory.pdf", page=2
        )
        assert result.citation() == "oop/design_patterns/factory.pdf (page 2)"

    def test_with_neither(self):
        result = self._result(
            course="operating_systems",
            topic="deadlocks",
            source_file="notes.txt",
            chunking_method="fixed_size",
        )
        assert result.citation() == "operating_systems/deadlocks/notes.txt"

    def test_with_both(self):
        result = self._result(
            course="oop",
            topic="design_patterns",
            source_file="factory.pdf",
            section="Factory Method Pattern",
            page=1,
        )
        assert result.citation() == "oop/design_patterns/factory.pdf > Factory Method Pattern (page 1)"


class TestRankingCorrectness:
    def test_ranks_by_cosine_similarity_to_query(self, store: NotesStore):
        """Uses ScriptedVoyageClient to give three chunks deliberate,
        hand-computed angular relationships to the query vector, so this
        asserts genuine cosine-similarity ranking behavior — not just that
        retrieve() returns *something* without erroring.
        """
        same_direction = _chunk(
            "dsa", "trees", "bst.md", 0, text="chunk pointing same direction as query"
        )
        forty_five_deg = _chunk("dsa", "trees", "bst.md", 1, text="chunk at 45 degrees from query")
        orthogonal = _chunk("dsa", "trees", "bst.md", 2, text="chunk orthogonal to query")
        query_text = "the query text"

        client = ScriptedVoyageClient(
            embeddings_by_text={
                same_direction.text: [1.0, 0.0],
                forty_five_deg.text: [1.0, 1.0],
                orthogonal.text: [0.0, 1.0],
                query_text: [1.0, 0.0],
            }
        )
        embedder = _embedder(client)
        embed_and_store([same_direction, forty_five_deg, orthogonal], embedder, store)

        results = retrieve(query_text, embedder, store, n_results=3)

        assert [r.chunk_index for r in results] == [0, 1, 2]
        assert results[0].score == pytest.approx(1.0)
        assert results[1].score == pytest.approx(1 / math.sqrt(2), abs=1e-4)
        assert results[2].score == pytest.approx(0.0, abs=1e-6)
        assert results[0].score > results[1].score > results[2].score

    def test_opposite_direction_scores_lowest(self, store: NotesStore):
        similar = _chunk("dsa", "trees", "bst.md", 0, text="similar chunk")
        opposite = _chunk("dsa", "trees", "bst.md", 1, text="opposite chunk")
        query_text = "query"

        client = ScriptedVoyageClient(
            embeddings_by_text={
                similar.text: [1.0, 0.0],
                opposite.text: [-1.0, 0.0],
                query_text: [1.0, 0.0],
            }
        )
        embedder = _embedder(client)
        embed_and_store([similar, opposite], embedder, store)

        results = retrieve(query_text, embedder, store, n_results=2)

        assert results[0].chunk_index == 0
        assert results[0].score == pytest.approx(1.0)
        assert results[1].chunk_index == 1
        assert results[1].score == pytest.approx(-1.0)


class TestRetrieveWithDefaults:
    def test_builds_real_embedder_and_store_then_delegates_to_retrieve(self, monkeypatch, store: NotesStore):
        """retrieve_with_defaults is a thin convenience wrapper around
        build_default_embedder() + NotesStore() + retrieve(). Rather than
        hitting the real Voyage API or the real on-disk store, monkeypatch
        those two factories at the module level and verify the wrapper
        wires their results into retrieve() with the right arguments.
        """
        fake_embedder = _embedder(FakeVoyageClient())
        monkeypatch.setattr(retriever_module, "build_default_embedder", lambda: fake_embedder)
        monkeypatch.setattr(retriever_module, "NotesStore", lambda: store)

        chunk = _chunk("dsa", "trees", "bst.md", 0, text="binary search tree")
        embed_and_store([chunk], fake_embedder, store)

        results = retrieve_with_defaults("bst", course_filter="dsa", n_results=2)

        assert len(results) == 1
        assert results[0].course == "dsa"
