from pathlib import Path

import pytest

from app.agent.conversation import Conversation
from app.embedding.pipeline import embed_and_store
from app.embedding.store import NotesStore
from app.ingestion.models import Chunk, ChunkMetadata
from tests.conftest import make_embedder as _embedder
from tests.fake_anthropic import FakeAnthropicClient, FakeMessage, FakeTextBlock, FakeToolUseBlock
from tests.fakes import FakeVoyageClient


def _chunk(course, topic, source_file, chunk_index, text) -> Chunk:
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


@pytest.fixture
def store(tmp_path: Path) -> NotesStore:
    s = NotesStore(persist_dir=tmp_path / "chroma", collection_name="test_notes")
    embed_and_store(
        [_chunk("dsa", "trees", "bst.md", 0, text="binary search tree")],
        _embedder(FakeVoyageClient()),
        s,
    )
    return s


class TestConversation:
    def test_first_message_starts_history(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[FakeMessage(content=[FakeTextBlock(text="hello there")], stop_reason="end_turn")]
        )
        convo = Conversation(client=client, embedder=_embedder(FakeVoyageClient()), store=store)

        result = convo.send("hi")

        assert result.text == "hello there"
        assert convo.messages[0] == {"role": "user", "content": "hi"}

    def test_second_message_includes_first_turns_history(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(content=[FakeTextBlock(text="answer one")], stop_reason="end_turn"),
                FakeMessage(content=[FakeTextBlock(text="answer two")], stop_reason="end_turn"),
            ]
        )
        convo = Conversation(client=client, embedder=_embedder(FakeVoyageClient()), store=store)

        convo.send("first question")
        convo.send("second question")

        second_call_messages = client.messages.calls[1]["messages"]
        user_texts = [m["content"] for m in second_call_messages if m["role"] == "user"]
        assert "first question" in user_texts
        assert "second question" in user_texts

    def test_tool_use_history_persists_across_turns(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[
                        FakeToolUseBlock(id="tu1", name="search_notes", input={"query": "bst"})
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(content=[FakeTextBlock(text="answer one")], stop_reason="end_turn"),
                FakeMessage(content=[FakeTextBlock(text="answer two")], stop_reason="end_turn"),
            ]
        )
        convo = Conversation(client=client, embedder=_embedder(FakeVoyageClient()), store=store)

        convo.send("what is a bst?")
        convo.send("follow-up question")

        # By the third API call, history should include the tool_use turn
        # and its tool_result from the first question.
        third_call_messages = client.messages.calls[2]["messages"]
        roles_and_shapes = [
            (m["role"], type(m["content"]).__name__ if not isinstance(m["content"], list) else "list")
            for m in third_call_messages
        ]
        assert ("user", "list") in roles_and_shapes  # the tool_result turn
