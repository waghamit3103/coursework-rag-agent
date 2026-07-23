"""Flask app factory. Takes client/embedder/store as arguments rather than
constructing them internally — same dependency-injection pattern used
throughout this codebase (Conversation, run_agent_turn, retrieve all take
their dependencies as arguments) — so tests can inject fakes and get a
real, fully-wired Flask app with zero network calls (see tests/test_api.py).
"""

from flask import Flask
from flask_cors import CORS

from app.api.routes import bp
from app.api.sessions import ConversationStore


def create_app(client, embedder, store) -> Flask:
    app = Flask(__name__)

    # Wide open for local dev, where the frontend runs on a different port
    # (Vite's default :5173) than the API (:5000). Stage 9 deployment
    # should restrict this to the actual deployed frontend origin instead
    # of leaving it open to any origin.
    CORS(app)

    app.config["NOTES_STORE"] = store
    app.config["CONVERSATION_STORE"] = ConversationStore(
        client=client, embedder=embedder, store=store
    )

    app.register_blueprint(bp)
    return app
