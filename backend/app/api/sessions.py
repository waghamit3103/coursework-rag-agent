"""In-memory conversation storage, keyed by a server-issued conversation_id.

Design decision — in-memory dict, not Redis/a database:
The Claude API itself is stateless (full history sent on every request);
"multi-turn" only requires *something* to hold that history between HTTP
requests. A plain in-process dict is the simplest thing that works, and is
adequate for this project's actual deployment shape — a single-instance
free-tier host (Stage 9). The known limitations are real and worth stating
plainly rather than glossing over: state is lost on restart, and it can't
be shared across multiple worker processes/instances. A production
version serving real concurrent users would move this to Redis (or pass
the full history from the client instead of keeping server-side state at
all) — noted here as a deliberate scope boundary, not an oversight.
"""

import uuid
from typing import Dict, Optional, Tuple

from app.agent.conversation import Conversation


class ConversationStore:
    def __init__(self, client, embedder, store):
        self._client = client
        self._embedder = embedder
        self._store = store
        self._conversations: Dict[str, Conversation] = {}

    def get_or_create(self, conversation_id: Optional[str]) -> Tuple[str, Conversation]:
        """If conversation_id is given and known, returns the existing
        Conversation (so history persists). If it's given but unknown —
        e.g. the server restarted and lost state, or the client sent a
        stale/bogus id — a fresh conversation is silently started under
        that same id, rather than erroring. This is a deliberate leniency
        choice: a dropped conversation losing context is a much better
        failure mode for a chat UI than a hard error the user can't
        recover from.
        """
        if conversation_id and conversation_id in self._conversations:
            return conversation_id, self._conversations[conversation_id]

        new_id = conversation_id or str(uuid.uuid4())
        conversation = Conversation(
            client=self._client, embedder=self._embedder, store=self._store
        )
        self._conversations[new_id] = conversation
        return new_id, conversation
