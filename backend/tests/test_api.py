import io
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


def _make_app(store: NotesStore, responses, raw_notes_dir: Path = None):
    client = FakeAnthropicClient(responses=responses)
    kwargs = {} if raw_notes_dir is None else {"raw_notes_dir": raw_notes_dir}
    app = create_app(
        client=client, embedder=_embedder(FakeVoyageClient()), store=store, **kwargs
    )
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


class TestUpload:
    def test_happy_path_saves_chunks_and_embeds(
        self, store: NotesStore, tmp_path: Path
    ):
        raw_notes_dir = tmp_path / "raw_notes"
        app, _ = _make_app(store, [], raw_notes_dir=raw_notes_dir)

        data = {
            "course": "DSA",
            "topic": "Linked Lists",
            "file": (
                io.BytesIO(b"# Linked Lists\n\nA linked list is a chain of nodes."),
                "notes.md",
            ),
        }
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["course"] == "dsa"
        assert body["topic"] == "linked-lists"
        assert body["files"] == [
            {"source_file": "notes.md", "chunks_embedded": body["chunks_embedded"]}
        ]
        assert body["chunks_embedded"] >= 1
        assert (raw_notes_dir / "dsa" / "linked-lists" / "notes.md").exists()
        assert "dsa" in store.distinct_courses()

    def test_multiple_files_in_one_request(self, store: NotesStore, tmp_path: Path):
        raw_notes_dir = tmp_path / "raw_notes"
        app, _ = _make_app(store, [], raw_notes_dir=raw_notes_dir)

        data = {
            "course": "dsa",
            "topic": "trees",
            "file": [
                (
                    io.BytesIO(b"# BST\n\nA binary search tree orders nodes by key."),
                    "bst.md",
                ),
                (io.BytesIO(b"an avl tree is a self-balancing bst"), "avl.txt"),
            ],
        }
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["course"] == "dsa"
        assert body["topic"] == "trees"
        source_files = {f["source_file"] for f in body["files"]}
        assert source_files == {"bst.md", "avl.txt"}
        assert all(f["chunks_embedded"] >= 1 for f in body["files"])
        assert body["chunks_embedded"] == sum(
            f["chunks_embedded"] for f in body["files"]
        )
        assert (raw_notes_dir / "dsa" / "trees" / "bst.md").exists()
        assert (raw_notes_dir / "dsa" / "trees" / "avl.txt").exists()

    def test_one_bad_extension_in_a_batch_rejects_whole_batch(
        self, store: NotesStore, tmp_path: Path
    ):
        raw_notes_dir = tmp_path / "raw_notes"
        app, _ = _make_app(store, [], raw_notes_dir=raw_notes_dir)

        data = {
            "course": "dsa",
            "topic": "trees",
            "file": [
                (io.BytesIO(b"good note content"), "good.txt"),
                (io.BytesIO(b"binary junk"), "bad.exe"),
            ],
        }
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 400
        assert "Unsupported file type" in resp.get_json()["error"]
        # Nothing from the batch should have been written to disk.
        assert not (raw_notes_dir / "dsa" / "trees" / "good.txt").exists()

    def test_missing_file_is_400(self, store: NotesStore, tmp_path: Path):
        app, _ = _make_app(store, [], raw_notes_dir=tmp_path / "raw_notes")
        resp = app.test_client().post(
            "/api/upload",
            data={"course": "dsa", "topic": "trees"},
            content_type="multipart/form-data",
        )

        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_unsupported_extension_is_400(self, store: NotesStore, tmp_path: Path):
        app, _ = _make_app(store, [], raw_notes_dir=tmp_path / "raw_notes")
        data = {
            "course": "dsa",
            "topic": "trees",
            "file": (io.BytesIO(b"binary junk"), "notes.exe"),
        }
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 400
        assert "Unsupported file type" in resp.get_json()["error"]

    def test_missing_course_or_topic_is_400(self, store: NotesStore, tmp_path: Path):
        app, _ = _make_app(store, [], raw_notes_dir=tmp_path / "raw_notes")
        data = {"topic": "trees", "file": (io.BytesIO(b"hello"), "notes.txt")}
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_empty_file_is_400_and_not_left_on_disk(
        self, store: NotesStore, tmp_path: Path
    ):
        raw_notes_dir = tmp_path / "raw_notes"
        app, _ = _make_app(store, [], raw_notes_dir=raw_notes_dir)
        data = {
            "course": "dsa",
            "topic": "trees",
            "file": (io.BytesIO(b"   \n\n   "), "empty.txt"),
        }
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 400
        assert not (raw_notes_dir / "dsa" / "trees" / "empty.txt").exists()

    def test_course_and_topic_are_slugified(self, store: NotesStore, tmp_path: Path):
        raw_notes_dir = tmp_path / "raw_notes"
        app, _ = _make_app(store, [], raw_notes_dir=raw_notes_dir)
        data = {
            "course": "  Operating Systems! ",
            "topic": "CPU Scheduling",
            "file": (
                io.BytesIO(
                    b"round robin scheduling gives each process a fixed time slice"
                ),
                "notes.txt",
            ),
        }
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["course"] == "operating-systems"
        assert body["topic"] == "cpu-scheduling"
        assert (
            raw_notes_dir / "operating-systems" / "cpu-scheduling" / "notes.txt"
        ).exists()

    def test_embedding_failure_returns_502_and_cleans_up_file(
        self, store: NotesStore, tmp_path: Path
    ):
        raw_notes_dir = tmp_path / "raw_notes"
        client = FakeAnthropicClient(responses=[])

        class BoomingEmbedder:
            def embed_documents(self, texts):
                raise RuntimeError("simulated Voyage API failure")

        from app.api.app import create_app as _create_app

        app = _create_app(
            client=client,
            embedder=BoomingEmbedder(),
            store=store,
            raw_notes_dir=raw_notes_dir,
        )
        app.config["TESTING"] = True

        data = {
            "course": "dsa",
            "topic": "trees",
            "file": (io.BytesIO(b"some real note content here"), "notes.txt"),
        }
        resp = app.test_client().post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert resp.status_code == 502
        body = resp.get_json()
        assert "RuntimeError" not in body["error"]
        assert not (raw_notes_dir / "dsa" / "trees" / "notes.txt").exists()
