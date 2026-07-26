from pathlib import Path

import pytest

from app.api.app import create_app
from app.embedding.pipeline import embed_and_store
from app.embedding.store import NotesStore
from app.ingestion.models import Chunk, ChunkMetadata
from tests.conftest import make_embedder as _embedder
from tests.fake_anthropic import (
    FakeAnthropicClient,
    FakeMessage,
    FakeTextBlock,
    FakeToolUseBlock,
)
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


def _text_response(text: str) -> FakeMessage:
    return FakeMessage(content=[FakeTextBlock(text=text)], stop_reason="end_turn")


@pytest.fixture
def store(tmp_path: Path) -> NotesStore:
    s = NotesStore(persist_dir=tmp_path / "chroma", collection_name="test_notes")
    embed_and_store(
        [_chunk("dsa", "trees", "bst.md", 0, text="binary search tree insertion")],
        _embedder(FakeVoyageClient()),
        s,
    )
    return s


def _make_app(store: NotesStore, responses):
    client = FakeAnthropicClient(responses=responses)
    app = create_app(client=client, embedder=_embedder(FakeVoyageClient()), store=store)
    app.config["TESTING"] = True
    return app, client


class TestHealth:
    def test_returns_ok(self, store: NotesStore):
        app, _ = _make_app(store, [])
        resp = app.test_client().get("/api/health")

        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}


class TestCourses:
    def test_returns_distinct_courses_from_store(self, store: NotesStore):
        app, _ = _make_app(store, [])
        resp = app.test_client().get("/api/courses")

        assert resp.status_code == 200
        assert resp.get_json() == {"courses": ["dsa"]}


class TestChat:
    def test_happy_path(self, store: NotesStore):
        app, _ = _make_app(store, [_text_response("a bst is a binary tree")])
        resp = app.test_client().post("/api/chat", json={"message": "what is a bst?"})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["answer"] == "a bst is a binary tree"
        assert isinstance(data["conversation_id"], str) and data["conversation_id"]
        assert isinstance(data["sources"], list)
        assert data["num_tool_calls"] == 0

    def test_response_with_sources_has_full_citation_shape(self, store: NotesStore):
        app, _ = _make_app(
            store,
            [
                FakeMessage(
                    content=[
                        FakeToolUseBlock(
                            id="tu1", name="search_notes", input={"query": "bst"}
                        )
                    ],
                    stop_reason="tool_use",
                ),
                _text_response("a bst is a binary tree"),
            ],
        )

        resp = app.test_client().post("/api/chat", json={"message": "what is a bst?"})

        data = resp.get_json()
        assert data["num_tool_calls"] == 1
        assert len(data["sources"]) == 1
        source = data["sources"][0]
        assert source["course"] == "dsa"
        assert source["topic"] == "trees"
        assert source["source_file"] == "bst.md"
        assert "score" in source
        assert "citation" in source

    def test_missing_message_is_400(self, store: NotesStore):
        app, _ = _make_app(store, [])
        resp = app.test_client().post("/api/chat", json={})

        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_blank_message_is_400(self, store: NotesStore):
        app, _ = _make_app(store, [])
        resp = app.test_client().post("/api/chat", json={"message": "   "})

        assert resp.status_code == 400

    def test_no_json_body_is_400_not_a_500(self, store: NotesStore):
        app, _ = _make_app(store, [])
        resp = app.test_client().post("/api/chat")

        assert resp.status_code == 400

    def test_conversation_id_returned_and_reusable(self, store: NotesStore):
        app, client = _make_app(
            store, [_text_response("answer one"), _text_response("answer two")]
        )
        test_client = app.test_client()

        first = test_client.post("/api/chat", json={"message": "first"}).get_json()
        cid = first["conversation_id"]

        second = test_client.post(
            "/api/chat", json={"message": "second", "conversation_id": cid}
        ).get_json()

        assert second["conversation_id"] == cid
        # The second call's history sent to Claude must include the first
        # question — proves conversation state genuinely persisted server
        # side across the two HTTP requests, not just that the same id
        # came back.
        second_call_messages = client.messages.calls[1]["messages"]
        user_texts = [m["content"] for m in second_call_messages if m["role"] == "user"]
        assert "first" in user_texts

    def test_unknown_conversation_id_starts_fresh_not_an_error(self, store: NotesStore):
        app, _ = _make_app(store, [_text_response("answer")])
        resp = app.test_client().post(
            "/api/chat", json={"message": "hi", "conversation_id": "totally-unknown-id"}
        )

        assert resp.status_code == 200
        assert resp.get_json()["conversation_id"] == "totally-unknown-id"

    def test_agent_failure_returns_502_with_clean_error_body(self, store: NotesStore):
        class BoomingMessages:
            def create(self, **kwargs):
                raise RuntimeError("simulated Claude API failure")

        class BoomingClient:
            def __init__(self):
                self.messages = BoomingMessages()

        app = create_app(
            client=BoomingClient(), embedder=_embedder(FakeVoyageClient()), store=store
        )
        app.config["TESTING"] = True

        resp = app.test_client().post("/api/chat", json={"message": "hi"})

        assert resp.status_code == 502
        body = resp.get_json()
        assert "error" in body
        assert "RuntimeError" not in body["error"]  # no leaked internals


class TestCORS:
    def test_default_origin_is_allowed(self, store: NotesStore, monkeypatch):
        monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
        app, _ = _make_app(store, [])

        resp = app.test_client().get(
            "/api/health", headers={"Origin": "http://localhost:5173"}
        )

        assert resp.access_control_allow_origin == "http://localhost:5173"

    def test_unlisted_origin_is_rejected(self, store: NotesStore, monkeypatch):
        monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
        app, _ = _make_app(store, [])

        resp = app.test_client().get(
            "/api/health", headers={"Origin": "https://evil.example.com"}
        )

        assert resp.access_control_allow_origin is None

    def test_deployed_origin_from_env_is_allowed(self, store: NotesStore, monkeypatch):
        monkeypatch.setenv("FRONTEND_ORIGIN", "https://coursework-rag-agent.vercel.app")
        app, _ = _make_app(store, [])

        resp = app.test_client().get(
            "/api/health",
            headers={"Origin": "https://coursework-rag-agent.vercel.app"},
        )

        assert (
            resp.access_control_allow_origin
            == "https://coursework-rag-agent.vercel.app"
        )

    def test_comma_separated_origins_both_allowed(self, store: NotesStore, monkeypatch):
        monkeypatch.setenv(
            "FRONTEND_ORIGIN",
            "http://localhost:5173,https://coursework-rag-agent.vercel.app",
        )
        app, _ = _make_app(store, [])
        test_client = app.test_client()

        local = test_client.get(
            "/api/health", headers={"Origin": "http://localhost:5173"}
        )
        deployed = test_client.get(
            "/api/health",
            headers={"Origin": "https://coursework-rag-agent.vercel.app"},
        )

        assert local.access_control_allow_origin == "http://localhost:5173"
        assert (
            deployed.access_control_allow_origin
            == "https://coursework-rag-agent.vercel.app"
        )
