from pathlib import Path

import pytest

from app.api.sessions import ConversationStore
from app.embedding.store import NotesStore
from app.embedding.voyage_client import VoyageEmbedder
from tests.fake_anthropic import FakeAnthropicClient
from tests.fakes import FakeVoyageClient


def _embedder(client) -> VoyageEmbedder:
    return VoyageEmbedder(client=client, batch_size=128, max_retries=1, retry_backoff_seconds=0.0)


@pytest.fixture
def store(tmp_path: Path) -> NotesStore:
    return NotesStore(persist_dir=tmp_path / "chroma", collection_name="test_notes")


@pytest.fixture
def conversation_store(store: NotesStore) -> ConversationStore:
    return ConversationStore(
        client=FakeAnthropicClient(responses=[]), embedder=_embedder(FakeVoyageClient()), store=store
    )


class TestConversationStore:
    def test_no_id_given_creates_a_new_one(self, conversation_store: ConversationStore):
        conversation_id, conversation = conversation_store.get_or_create(None)

        assert conversation_id
        assert conversation.messages == []

    def test_known_id_returns_the_same_conversation_object(
        self, conversation_store: ConversationStore
    ):
        first_id, first_conversation = conversation_store.get_or_create(None)
        second_id, second_conversation = conversation_store.get_or_create(first_id)

        assert first_id == second_id
        assert first_conversation is second_conversation

    def test_unknown_id_starts_fresh_under_that_same_id(
        self, conversation_store: ConversationStore
    ):
        conversation_id, conversation = conversation_store.get_or_create("some-unknown-id")

        assert conversation_id == "some-unknown-id"
        assert conversation.messages == []

    def test_two_different_unknown_ids_get_independent_conversations(
        self, conversation_store: ConversationStore
    ):
        _, convo_a = conversation_store.get_or_create(None)
        _, convo_b = conversation_store.get_or_create(None)

        assert convo_a is not convo_b
