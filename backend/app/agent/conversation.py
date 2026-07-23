"""Multi-turn conversation state. The Claude API is stateless — each
request carries the full message history — so "multi-turn" just means
holding onto that history between calls and appending to it.
"""

from dataclasses import dataclass, field
from typing import List

from app import config
from app.agent.loop import AgentTurnResult, run_agent_turn
from app.embedding.store import NotesStore
from app.embedding.voyage_client import VoyageEmbedder


@dataclass
class Conversation:
    client: object
    embedder: VoyageEmbedder
    store: NotesStore
    messages: List[dict] = field(default_factory=list)

    def send(self, user_text: str) -> AgentTurnResult:
        self.messages.append({"role": "user", "content": user_text})

        result = run_agent_turn(
            self.client,
            self.messages,
            self.embedder,
            self.store,
            model=config.CLAUDE_MODEL,
            max_tokens=config.CLAUDE_MAX_TOKENS,
            effort=config.CLAUDE_EFFORT,
            max_tool_iterations=config.MAX_TOOL_ITERATIONS,
        )
        self.messages = result.messages
        return result
