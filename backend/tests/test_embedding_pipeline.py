from pathlib import Path

from app.embedding.pipeline import embed_and_store
from app.embedding.store import NotesStore
from app.embedding.voyage_client import VoyageEmbedder
from app.ingestion.models import Chunk, ChunkMetadata
from tests.fakes import FakeVoyageClient


def _chunk(course, topic, source_file, chunk_index, text="chunk text") -> Chunk:
    return Chunk(
        text=text,
        metadata=ChunkMetadata(
            course=course,
            topic=topic,
            source_file=source_file,
            chunk_index=chunk_index,
            chunking_method="heading",
        ),
    )


def _embedder(client) -> VoyageEmbedder:
    return VoyageEmbedder(
        client=client, batch_size=128, max_retries=1, retry_backoff_seconds=0.0
    )


def test_embeds_and_stores_all_chunks(tmp_path: Path):
    chunks = [
        _chunk("dsa", "trees", "bst.md", 0),
        _chunk("dsa", "trees", "bst.md", 1),
        _chunk("operating_systems", "scheduling", "sched.md", 0),
    ]
    store = NotesStore(persist_dir=tmp_path / "chroma")
    stats = embed_and_store(chunks, _embedder(FakeVoyageClient()), store)

    assert stats.chunks_embedded == 3
    assert stats.files_processed == 2
    assert store.count() == 3


def test_batches_the_embed_call_across_files_not_per_file(tmp_path: Path):
    """Regression test: an earlier version called embed_documents() once
    per source file, which multiplies Voyage API calls (and rate-limit
    exposure) by file count for no benefit. All chunks across all files
    should be embedded in as few calls as VOYAGE_EMBED_BATCH_SIZE allows —
    a single call here, since 3 texts fits in one batch of 128.
    """
    chunks = [
        _chunk("dsa", "trees", "bst.md", 0),
        _chunk("dsa", "trees", "bst.md", 1),
        _chunk("dsa", "sorting", "sort.md", 0),
    ]
    store = NotesStore(persist_dir=tmp_path / "chroma")
    client = FakeVoyageClient()
    embed_and_store(chunks, _embedder(client), store)

    assert len(client.calls) == 1
    assert len(client.calls[0]["texts"]) == 3


def test_respects_batch_size_across_the_whole_corpus(tmp_path: Path):
    chunks = [_chunk("dsa", "trees", "bst.md", i) for i in range(5)]
    store = NotesStore(persist_dir=tmp_path / "chroma")
    client = FakeVoyageClient()
    embedder = VoyageEmbedder(
        client=client, batch_size=2, max_retries=1, retry_backoff_seconds=0.0
    )

    embed_and_store(chunks, embedder, store)

    # 5 chunks, batch_size=2 -> 3 calls of sizes 2, 2, 1 regardless of the
    # fact that they're all one source file.
    assert [len(c["texts"]) for c in client.calls] == [2, 2, 1]


def test_reembedding_replaces_stale_chunks_for_a_file(tmp_path: Path):
    store = NotesStore(persist_dir=tmp_path / "chroma")
    embedder = _embedder(FakeVoyageClient())

    first_run = [
        _chunk("dsa", "trees", "bst.md", 0),
        _chunk("dsa", "trees", "bst.md", 1),
        _chunk("dsa", "trees", "bst.md", 2),
    ]
    embed_and_store(first_run, embedder, store)
    assert store.count() == 3

    # File shrank to a single chunk after an edit — re-running must not
    # leave chunk_index 1 and 2 behind as orphans.
    second_run = [_chunk("dsa", "trees", "bst.md", 0, text="edited content")]
    embed_and_store(second_run, embedder, store)
    assert store.count() == 1


def test_leaves_other_files_untouched_on_reembed(tmp_path: Path):
    store = NotesStore(persist_dir=tmp_path / "chroma")
    embedder = _embedder(FakeVoyageClient())

    embed_and_store(
        [
            _chunk("dsa", "trees", "bst.md", 0),
            _chunk("dsa", "sorting", "sort.md", 0),
        ],
        embedder,
        store,
    )
    assert store.count() == 2

    # Re-embed only bst.md.
    embed_and_store([_chunk("dsa", "trees", "bst.md", 0, text="edited")], embedder, store)

    assert store.count() == 2
