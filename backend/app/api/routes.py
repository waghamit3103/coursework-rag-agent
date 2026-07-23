"""REST endpoints. Kept thin — request parsing and HTTP-shape concerns
only; the actual work (retrieval, agent orchestration) lives in app.agent
and app.retrieval, unchanged from how they're used by scripts/chat.py.
Same code path either way means the API can't drift from what's already
been tested and manually verified via the CLI.
"""

from flask import Blueprint, current_app, jsonify, request

from app.retrieval.retriever import RetrievedChunk

bp = Blueprint("api", __name__, url_prefix="/api")


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
