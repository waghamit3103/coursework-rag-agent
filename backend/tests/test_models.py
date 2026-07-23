from app.ingestion.models import Chunk, ChunkMetadata, chunk_id


def _make_chunk(**overrides) -> Chunk:
    defaults = dict(
        course="dsa",
        topic="trees",
        source_file="bst.md",
        chunk_index=2,
        chunking_method="heading",
        section="Insertion",
        page=None,
    )
    defaults.update(overrides)
    return Chunk(text="some chunk text", metadata=ChunkMetadata(**defaults))


class TestChunkId:
    def test_format(self):
        chunk = _make_chunk()
        assert chunk_id(chunk) == "dsa/trees/bst.md#2"

    def test_differs_by_chunk_index(self):
        a = _make_chunk(chunk_index=0)
        b = _make_chunk(chunk_index=1)
        assert chunk_id(a) != chunk_id(b)

    def test_differs_by_source_file(self):
        a = _make_chunk(source_file="bst.md")
        b = _make_chunk(source_file="avl.md")
        assert chunk_id(a) != chunk_id(b)

    def test_differs_by_course_and_topic(self):
        a = _make_chunk(course="dsa", topic="trees")
        b = _make_chunk(course="oop", topic="trees")
        assert chunk_id(a) != chunk_id(b)


class TestToChromaMetadata:
    def test_strips_none_values(self):
        chunk = _make_chunk(section="Insertion", page=None)
        meta = chunk.metadata.to_chroma_metadata()
        assert "page" not in meta
        assert meta["section"] == "Insertion"

    def test_keeps_present_optional_fields(self):
        chunk = _make_chunk(section=None, page=3)
        meta = chunk.metadata.to_chroma_metadata()
        assert "section" not in meta
        assert meta["page"] == 3

    def test_always_keeps_required_fields(self):
        chunk = _make_chunk(section=None, page=None)
        meta = chunk.metadata.to_chroma_metadata()
        assert meta == {
            "course": "dsa",
            "topic": "trees",
            "source_file": "bst.md",
            "chunk_index": 2,
            "chunking_method": "heading",
        }
