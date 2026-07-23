from pathlib import Path

import pytest

from app.embedding.store import NotesStore
from app.ingestion.models import Chunk, ChunkMetadata


def _chunk(course, topic, source_file, chunk_index, section=None, page=None) -> Chunk:
    return Chunk(
        text=f"text for {source_file}#{chunk_index}",
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


class TestUpsertChunks:
    def test_stores_and_retrieves_by_id(self, store: NotesStore):
        chunks = [_chunk("dsa", "trees", "bst.md", 0, section="Intro")]
        store.upsert_chunks(chunks, embeddings=[[0.1, 0.2]])

        assert store.count() == 1

    def test_rejects_mismatched_lengths(self, store: NotesStore):
        chunks = [_chunk("dsa", "trees", "bst.md", 0)]
        with pytest.raises(ValueError):
            store.upsert_chunks(chunks, embeddings=[[0.1], [0.2]])

    def test_empty_input_is_a_no_op(self, store: NotesStore):
        store.upsert_chunks([], embeddings=[])
        assert store.count() == 0

    def test_optional_metadata_fields_omitted_when_none(self, store: NotesStore):
        chunks = [_chunk("dsa", "trees", "bst.md", 0, section=None, page=None)]
        store.upsert_chunks(chunks, embeddings=[[0.1, 0.2]])

        result = store.query(query_embedding=[0.1, 0.2], n_results=1)
        metadata = result["metadatas"][0][0]
        assert "section" not in metadata
        assert "page" not in metadata

    def test_upsert_same_id_overwrites_not_duplicates(self, store: NotesStore):
        chunk_v1 = _chunk("dsa", "trees", "bst.md", 0, section="Old Title")
        store.upsert_chunks([chunk_v1], embeddings=[[0.1, 0.2]])

        chunk_v2 = _chunk("dsa", "trees", "bst.md", 0, section="New Title")
        store.upsert_chunks([chunk_v2], embeddings=[[0.3, 0.4]])

        assert store.count() == 1
        result = store.query(query_embedding=[0.3, 0.4], n_results=1)
        assert result["metadatas"][0][0]["section"] == "New Title"


class TestDeleteBySourceFile:
    def test_deletes_only_matching_file(self, store: NotesStore):
        store.upsert_chunks(
            [
                _chunk("dsa", "trees", "bst.md", 0),
                _chunk("dsa", "trees", "bst.md", 1),
                _chunk("dsa", "sorting", "sort.md", 0),
            ],
            embeddings=[[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]],
        )

        store.delete_by_source_file("dsa", "trees", "bst.md")

        assert store.count() == 1

    def test_no_op_when_nothing_matches(self, store: NotesStore):
        store.upsert_chunks(
            [_chunk("dsa", "trees", "bst.md", 0)], embeddings=[[0.1, 0.1]]
        )

        store.delete_by_source_file("oop", "design_patterns", "nonexistent.md")

        assert store.count() == 1

    def test_reembedding_a_shrunk_file_leaves_no_orphans(self, store: NotesStore):
        # First "ingestion": file produced 3 chunks.
        store.upsert_chunks(
            [
                _chunk("dsa", "trees", "bst.md", 0),
                _chunk("dsa", "trees", "bst.md", 1),
                _chunk("dsa", "trees", "bst.md", 2),
            ],
            embeddings=[[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]],
        )
        assert store.count() == 3

        # File edited, now only produces 1 chunk. Re-embedding must clear
        # the stale chunk_index 1 and 2 entries, not just overwrite index 0.
        store.delete_by_source_file("dsa", "trees", "bst.md")
        store.upsert_chunks(
            [_chunk("dsa", "trees", "bst.md", 0)], embeddings=[[0.9, 0.9]]
        )

        assert store.count() == 1


class TestQuery:
    def test_supports_course_filter(self, store: NotesStore):
        store.upsert_chunks(
            [
                _chunk("dsa", "trees", "bst.md", 0),
                _chunk("operating_systems", "scheduling", "sched.md", 0),
            ],
            embeddings=[[1.0, 0.0], [1.0, 0.0]],
        )

        result = store.query(
            query_embedding=[1.0, 0.0], n_results=5, where={"course": "dsa"}
        )

        assert len(result["ids"][0]) == 1
        assert result["metadatas"][0][0]["course"] == "dsa"
