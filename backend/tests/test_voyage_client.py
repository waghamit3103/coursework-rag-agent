import pytest

from app.embedding.voyage_client import VoyageEmbedder, VoyageEmbeddingError
from tests.fakes import FakeVoyageClient


def _embedder(client=None, **kwargs) -> VoyageEmbedder:
    return VoyageEmbedder(
        client=client or FakeVoyageClient(),
        model="voyage-3-large",
        output_dimension=1024,
        batch_size=kwargs.pop("batch_size", 128),
        max_retries=kwargs.pop("max_retries", 3),
        retry_backoff_seconds=kwargs.pop("retry_backoff_seconds", 0.0),
        sleep_fn=kwargs.pop("sleep_fn", lambda _seconds: None),
    )


class TestEmbedDocuments:
    def test_single_batch_preserves_order(self):
        client = FakeVoyageClient()
        embedder = _embedder(client, batch_size=128)

        result = embedder.embed_documents(["a", "bb", "ccc"])

        assert result.embeddings == [[1.0], [2.0], [3.0]]
        assert len(client.calls) == 1
        assert client.calls[0]["input_type"] == "document"
        assert client.calls[0]["model"] == "voyage-3-large"
        assert client.calls[0]["output_dimension"] == 1024

    def test_splits_into_multiple_batches(self):
        client = FakeVoyageClient()
        embedder = _embedder(client, batch_size=2)

        texts = ["a", "bb", "ccc", "dddd", "e"]
        result = embedder.embed_documents(texts)

        # 5 texts, batch_size 2 -> 3 calls of sizes 2, 2, 1
        assert [len(c["texts"]) for c in client.calls] == [2, 2, 1]
        # Results still reassembled in original order across batches.
        assert result.embeddings == [[1.0], [2.0], [3.0], [4.0], [1.0]]

    def test_total_tokens_summed_across_batches(self):
        client = FakeVoyageClient()
        embedder = _embedder(client, batch_size=1)

        result = embedder.embed_documents(["one two", "three four five"])

        assert result.total_tokens == 2 + 3

    def test_empty_input_makes_no_calls(self):
        client = FakeVoyageClient()
        embedder = _embedder(client)

        result = embedder.embed_documents([])

        assert result.embeddings == []
        assert client.calls == []


class TestEmbedQuery:
    def test_uses_query_input_type(self):
        client = FakeVoyageClient()
        embedder = _embedder(client)

        embedding = embedder.embed_query("what is a binary search tree?")

        assert client.calls[0]["input_type"] == "query"
        assert embedding == [float(len("what is a binary search tree?"))]


class TestRetry:
    def test_succeeds_after_transient_failures(self):
        client = FakeVoyageClient(fail_times=2)
        embedder = _embedder(client, max_retries=3)

        result = embedder.embed_documents(["hello"])

        assert result.embeddings == [[5.0]]
        assert len(client.calls) == 3  # 2 failures + 1 success

    def test_gives_up_after_max_retries(self):
        client = FakeVoyageClient(fail_times=10)
        embedder = _embedder(client, max_retries=3)

        with pytest.raises(VoyageEmbeddingError):
            embedder.embed_documents(["hello"])

        assert len(client.calls) == 3

    def test_backoff_delay_doubles_between_attempts(self):
        sleeps = []
        client = FakeVoyageClient(fail_times=2)
        embedder = _embedder(
            client,
            max_retries=3,
            retry_backoff_seconds=1.0,
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )

        embedder.embed_documents(["hello"])

        assert sleeps == [1.0, 2.0]
