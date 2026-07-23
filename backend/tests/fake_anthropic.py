"""Test double for the Anthropic client, used to test the agent loop
without a network call. Scripted: construct with a list of FakeMessage
responses, and successive client.messages.create(...) calls return them
in order — lets a test script an exact multi-turn tool-use exchange
(search -> weak results -> refined search -> final answer, etc.) and
assert the loop's behavior deterministically.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeStopDetails:
    category: Optional[str] = None
    explanation: Optional[str] = None


@dataclass
class FakeMessage:
    content: list
    stop_reason: str
    stop_details: Optional[FakeStopDetails] = None


@dataclass
class FakeMessagesResource:
    responses: List[FakeMessage]
    calls: List[dict] = field(default_factory=list)
    _index: int = field(default=0, init=False)

    def create(self, **kwargs) -> FakeMessage:
        # Snapshot `messages` at call time — the caller's list is mutated
        # (appended to) after this call returns, so storing the reference
        # as-is would make every recorded call's "messages" retroactively
        # show the *final* history instead of what was actually sent.
        snapshot = dict(kwargs)
        if "messages" in snapshot:
            snapshot["messages"] = list(snapshot["messages"])
        self.calls.append(snapshot)

        response = self.responses[self._index]
        self._index += 1
        return response


@dataclass
class FakeAnthropicClient:
    responses: List[FakeMessage]
    messages: FakeMessagesResource = field(init=False)

    def __post_init__(self) -> None:
        self.messages = FakeMessagesResource(responses=list(self.responses))
