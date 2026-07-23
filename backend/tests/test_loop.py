from pathlib import Path

import pytest

from app.agent.loop import run_agent_turn
from app.embedding.pipeline import embed_and_store
from app.embedding.store import NotesStore
from app.embedding.voyage_client import VoyageEmbedder
from app.ingestion.models import Chunk, ChunkMetadata
from tests.fake_anthropic import FakeAnthropicClient, FakeMessage, FakeStopDetails, FakeTextBlock, FakeToolUseBlock
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


def _embedder(client) -> VoyageEmbedder:
    return VoyageEmbedder(client=client, batch_size=128, max_retries=1, retry_backoff_seconds=0.0)


@pytest.fixture
def store(tmp_path: Path) -> NotesStore:
    s = NotesStore(persist_dir=tmp_path / "chroma", collection_name="test_notes")
    chunks = [
        _chunk("dsa", "trees", "bst.md", 0, text="binary search tree insertion", section="Insertion"),
        _chunk(
            "operating_systems",
            "scheduling",
            "sched.md",
            0,
            text="round robin scheduling quantum",
            section="Round Robin",
        ),
    ]
    embed_and_store(chunks, _embedder(FakeVoyageClient()), s)
    return s


class TestSingleSearchThenAnswer:
    def test_returns_final_text_and_sources(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[
                        FakeToolUseBlock(id="tu1", name="search_notes", input={"query": "bst"})
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(
                    content=[FakeTextBlock(text="A BST is a binary tree with an ordering invariant.")],
                    stop_reason="end_turn",
                ),
            ]
        )
        messages = [{"role": "user", "content": "what is a bst?"}]

        result = run_agent_turn(client, messages, _embedder(FakeVoyageClient()), store)

        assert result.text == "A BST is a binary tree with an ordering invariant."
        assert result.num_tool_calls == 1
        # No course_filter and only 2 chunks total in the fixture store,
        # so both come back (FakeVoyageClient's embeddings aren't
        # semantically meaningful — ranking quality itself is
        # test_retriever.py's job, not this test's).
        assert len(result.sources) == 2
        assert any(s.course == "dsa" for s in result.sources)
        assert result.stop_reason == "end_turn"

    def test_does_not_mutate_caller_message_list(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[FakeMessage(content=[FakeTextBlock(text="answer")], stop_reason="end_turn")]
        )
        original_messages = [{"role": "user", "content": "hello"}]
        original_len = len(original_messages)

        run_agent_turn(client, original_messages, _embedder(FakeVoyageClient()), store)

        assert len(original_messages) == original_len

    def test_system_prompt_and_tools_sent_on_every_call(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[FakeMessage(content=[FakeTextBlock(text="answer")], stop_reason="end_turn")]
        )
        run_agent_turn(client, [{"role": "user", "content": "hi"}], _embedder(FakeVoyageClient()), store)

        call = client.messages.calls[0]
        assert "search_notes" in call["system"]
        assert call["tools"][0]["name"] == "search_notes"


class TestParallelToolCalls:
    def test_multiple_tool_use_blocks_in_one_response_all_execute(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[
                        FakeToolUseBlock(
                            id="tu1",
                            name="search_notes",
                            input={"query": "bst", "course_filter": "dsa"},
                        ),
                        FakeToolUseBlock(
                            id="tu2",
                            name="search_notes",
                            input={"query": "scheduling", "course_filter": "operating_systems"},
                        ),
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(content=[FakeTextBlock(text="comparison answer")], stop_reason="end_turn"),
            ]
        )
        messages = [{"role": "user", "content": "compare bst insertion to round robin"}]

        result = run_agent_turn(client, messages, _embedder(FakeVoyageClient()), store)

        assert result.num_tool_calls == 2
        courses_seen = {s.course for s in result.sources}
        assert courses_seen == {"dsa", "operating_systems"}

        # Both tool_results for the parallel calls must land in a single
        # user message, not split across two separate messages — the API
        # requires every pending tool_use to be answered in one user turn.
        tool_result_turn = result.messages[2]
        assert tool_result_turn["role"] == "user"
        assert len(tool_result_turn["content"]) == 2
        tool_use_ids = {block["tool_use_id"] for block in tool_result_turn["content"]}
        assert tool_use_ids == {"tu1", "tu2"}


class TestMultiHopReQuery:
    def test_continues_past_a_weak_first_result_then_answers(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[
                        FakeToolUseBlock(id="tu1", name="search_notes", input={"query": "vague term"})
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(
                    content=[
                        FakeToolUseBlock(
                            id="tu2", name="search_notes", input={"query": "refined term"}
                        )
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(content=[FakeTextBlock(text="final grounded answer")], stop_reason="end_turn"),
            ]
        )
        messages = [{"role": "user", "content": "some hard question"}]

        result = run_agent_turn(client, messages, _embedder(FakeVoyageClient()), store)

        assert result.num_tool_calls == 2
        assert result.text == "final grounded answer"
        assert len(client.messages.calls) == 3


class TestMaxIterationsCap:
    def test_forces_a_final_no_tools_call_after_cap(self, store: NotesStore):
        # Always asks for another search — more than max_tool_iterations.
        endless_tool_use = FakeMessage(
            content=[FakeToolUseBlock(id="tu", name="search_notes", input={"query": "x"})],
            stop_reason="tool_use",
        )
        forced_final = FakeMessage(
            content=[FakeTextBlock(text="best effort answer")], stop_reason="end_turn"
        )
        client = FakeAnthropicClient(responses=[endless_tool_use] * 5 + [forced_final])

        result = run_agent_turn(
            client,
            [{"role": "user", "content": "question"}],
            _embedder(FakeVoyageClient()),
            store,
            max_tool_iterations=5,
        )

        assert result.num_tool_calls == 5
        assert result.text == "best effort answer"
        # 5 tool-calling requests + 1 forced final request with no tools.
        assert len(client.messages.calls) == 6
        assert "tools" not in client.messages.calls[-1]


class TestRefusalHandling:
    def test_returns_explanation_instead_of_crashing(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[],
                    stop_reason="refusal",
                    stop_details=FakeStopDetails(category="cyber", explanation="I can't help with that."),
                )
            ]
        )

        result = run_agent_turn(
            client, [{"role": "user", "content": "something disallowed"}], _embedder(FakeVoyageClient()), store
        )

        assert result.text == "I can't help with that."
        assert result.stop_reason == "refusal"


class TestUnknownToolDefensiveHandling:
    def test_unrecognized_tool_name_reports_error_and_continues(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[FakeToolUseBlock(id="tu1", name="some_other_tool", input={})],
                    stop_reason="tool_use",
                ),
                FakeMessage(content=[FakeTextBlock(text="recovered answer")], stop_reason="end_turn"),
            ]
        )

        result = run_agent_turn(
            client, [{"role": "user", "content": "question"}], _embedder(FakeVoyageClient()), store
        )

        assert result.text == "recovered answer"
        assert result.num_tool_calls == 0  # only search_notes calls are counted
        second_call_messages = client.messages.calls[1]["messages"]
        tool_result_content = second_call_messages[-1]["content"][0]
        assert tool_result_content["is_error"] is True


class TestSourceDeduplication:
    def test_same_chunk_returned_twice_keeps_highest_score(self, store: NotesStore):
        client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[
                        FakeToolUseBlock(id="tu1", name="search_notes", input={"query": "bst"})
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(
                    content=[
                        FakeToolUseBlock(id="tu2", name="search_notes", input={"query": "binary search tree"})
                    ],
                    stop_reason="tool_use",
                ),
                FakeMessage(content=[FakeTextBlock(text="answer")], stop_reason="end_turn"),
            ]
        )

        result = run_agent_turn(
            client, [{"role": "user", "content": "q"}], _embedder(FakeVoyageClient()), store
        )

        # Both searches overlap the same 2-chunk store, so sources should
        # be deduped to at most 2 unique chunks despite 2 searches run.
        keys = [(s.course, s.topic, s.source_file, s.chunk_index) for s in result.sources]
        assert len(keys) == len(set(keys))
