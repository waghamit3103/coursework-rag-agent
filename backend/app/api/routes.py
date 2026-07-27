"""REST endpoints. Kept thin — request parsing and HTTP-shape concerns
only; the actual work (retrieval, agent orchestration) lives in app.agent
and app.retrieval, unchanged from how they're used by scripts/chat.py.
Same code path either way means the API can't drift from what's already
been tested and manually verified via the CLI.
"""

import re
from collections import defaultdict
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from app import config
from app.embedding.pipeline import embed_and_store
from app.ingestion.pipeline import chunk_file
from app.retrieval.retriever import RetrievedChunk

bp = Blueprint("api", __name__, url_prefix="/api")

# Course/topic double as directory names on disk (same taxonomy the bulk
# ingestion pipeline uses — see ingestion/pipeline.py), so free-form user
# input is slugified rather than used raw: this is what keeps a value like
# "../../etc" or "Data Structures!" from ever becoming a literal path
# segment.
_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    return _SLUG_COLLAPSE_RE.sub("-", value.strip().lower()).strip("-")


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@bp.route("/courses", methods=["GET"])
def courses():
    notes_store = current_app.config["NOTES_STORE"]
    return jsonify({"courses": notes_store.distinct_courses()})


@bp.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    conversation_store = current_app.config["CONVERSATION_STORE"]
    conversation_id, conversation = conversation_store.get_or_create(
        payload.get("conversation_id")
    )

    try:
        result = conversation.send(message)
    except Exception:
        # Don't leak internals (API errors, stack traces) to the client —
        # log server-side for debugging, return a clean, generic error.
        current_app.logger.exception("Agent turn failed")
        return (
            jsonify(
                {"error": "The agent failed to produce a response. Please try again."}
            ),
            502,
        )

    return jsonify(
        {
            "conversation_id": conversation_id,
            "answer": result.text,
            "sources": [_source_to_dict(s) for s in result.sources],
            "num_tool_calls": result.num_tool_calls,
        }
    )


@bp.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("file")
    if not files or all(not f.filename for f in files):
        return jsonify({"error": "at least one file is required"}), 400

    course = _slugify(request.form.get("course", ""))
    topic = _slugify(request.form.get("topic", ""))
    if not course or not topic:
        return jsonify({"error": "course and topic are required"}), 400

    # Validate every file up front, before touching disk — a batch either
    # saves in full or not at all, rather than silently landing a partial
    # set of files if the 3rd of 5 has a bad extension.
    saves = []  # (werkzeug FileStorage, dest_path, filename)
    for f in files:
        if not f.filename:
            continue

        ext = Path(f.filename).suffix.lower()
        if ext not in config.SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(config.SUPPORTED_EXTENSIONS))
            return (
                jsonify(
                    {
                        "error": f"Unsupported file type '{ext}' ({f.filename}). "
                        f"Supported types: {supported}"
                    }
                ),
                400,
            )

        filename = secure_filename(f.filename)
        if not filename:
            return jsonify({"error": f"invalid filename: {f.filename}"}), 400

        saves.append((f, filename))

    raw_notes_dir = current_app.config["RAW_NOTES_DIR"]
    dest_dir = raw_notes_dir / course / topic
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for f, filename in saves:
        dest_path = dest_dir / filename
        f.save(dest_path)
        saved_paths.append(dest_path)

    try:
        chunks = []
        for dest_path in saved_paths:
            chunks.extend(chunk_file(dest_path, raw_notes_dir))

        if not chunks:
            for dest_path in saved_paths:
                dest_path.unlink(missing_ok=True)
            return (
                jsonify({"error": "No content could be extracted from these files"}),
                400,
            )

        embedder = current_app.config["EMBEDDER"]
        notes_store = current_app.config["NOTES_STORE"]
        # One embed_and_store call across every file's chunks, not one per
        # file — same batching rationale as the bulk ingestion pipeline
        # (see embedding/pipeline.py): fewer Voyage API round trips, and
        # deletion of stale chunks still happens per source file inside it.
        stats = embed_and_store(chunks, embedder, notes_store)
    except Exception:
        # Same leak-nothing-to-the-client posture as /chat's error handling:
        # a bad PDF or a Voyage API hiccup shouldn't surface a stack trace,
        # and shouldn't leave half-indexed files sitting on disk either.
        for dest_path in saved_paths:
            dest_path.unlink(missing_ok=True)
        current_app.logger.exception("Failed to process uploaded file(s)")
        return (
            jsonify(
                {"error": "Failed to process the uploaded file(s). Please try again."}
            ),
            502,
        )

    chunks_by_file = defaultdict(int)
    for chunk in chunks:
        chunks_by_file[chunk.metadata.source_file] += 1

    return jsonify(
        {
            "course": course,
            "topic": topic,
            "files": [
                {
                    "source_file": dest_path.name,
                    "chunks_embedded": chunks_by_file[dest_path.name],
                }
                for dest_path in saved_paths
            ],
            "chunks_embedded": stats.chunks_embedded,
        }
    )


def _source_to_dict(source: RetrievedChunk) -> dict:
    return {
        "course": source.course,
        "topic": source.topic,
        "source_file": source.source_file,
        "section": source.section,
        "page": source.page,
        "score": source.score,
        "citation": source.citation(),
    }
