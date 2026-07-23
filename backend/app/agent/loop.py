"""The agent loop: send the conversation to Claude, execute any
search_notes tool calls, feed results back, repeat until Claude produces a
final answer (or the iteration cap is hit).

Design decision — manual loop, not the SDK's beta Tool Runner:
The Anthropic SDK ships a `client.beta.messages.tool_runner()` helper that
hides this loop entirely. Using it would mean less code, but it also means
the exact mechanics — when a tool call happens, how results feed back,
what "the model is done" looks like, how multiple tool calls in one turn
are handled — would live inside a beta SDK helper instead of being visible,
testable, and explainable line by line. Given this project's whole point
is demonstrating (and being able to defend, in an interview) an
understanding of how an agent loop actually works, hand-writing it is the
right trade-off here — the Tool Runner's main selling point ("don't have
to write the loop yourself") is exactly the thing worth being able to
explain in this project. It also means zero beta-API dependency: the loop
is built entirely on the stable `client.messages.create` surface.

Design decision — the loop doesn't decide *when* to re-query; it only
executes what Claude asks for:
See prompts.py's docstring — the "evaluate results, re-query if needed"
behavior is the model's own judgment, driven by the system prompt. The
loop's job is mechanical: run tool calls, feed results back, stop when
Claude stops asking for tools. This keeps the harness simple and keeps the
actual agentic decision-making where it belongs (in the model), rather
than the harness trying to second-guess whether a result set was "good
enough."
"""

from dataclasses import dataclass, field
from typing import List, Optional

from app import config
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import SEARCH_NOTES_TOOL_NAME, build_search_notes_tool, execute_search_notes
from app.embedding.store import NotesStore
from app.embedding.voyage_client import VoyageEmbedder
from app.retrieval.retriever import RetrievedChunk


@dataclass
class AgentTurnResult:
    text: str
    sources: List[RetrievedChunk]
    messages: List[dict]
    num_tool_calls: int
    stop_reason: Optional[str] = None


def run_agent_turn(
    client,
    messages: List[dict],
    embedder: VoyageEmbedder,
    store: NotesStore,
    model: str = config.CLAUDE_MODEL,
    max_tokens: int = config.CLAUDE_MAX_TOKENS,
    effort: str = config.CLAUDE_EFFORT,
    max_tool_iterations: int = config.MAX_TOOL_ITERATIONS,
) -> AgentTurnResult:
    """Run the loop for one user turn. `messages` must already include the
    new user message; this function appends every assistant/tool_result
    turn it produces and returns the full updated history (so a caller —
    Conversation, below, or Stage 5's API — can pass it straight back in
    on the next call for multi-turn context).
    """
    messages = list(messages)  # don't mutate the caller's list
    tools = [build_search_notes_tool(store)]
    sources: List[RetrievedChunk] = []
    num_tool_calls = 0

    for _ in range(max_tool_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
            output_config={"effort": effort},
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return AgentTurnResult(
                text=_extract_final_text(response),
                sources=_dedupe_sources(sources),
                messages=messages,
                num_tool_calls=num_tool_calls,
                stop_reason=response.stop_reason,
            )

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            # Only one tool exists right now; this guard is here so a
            # future second tool doesn't silently get routed through
            # search_notes's executor.
            if block.name != SEARCH_NOTES_TOOL_NAME:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Unknown tool: {block.name}",
                        "is_error": True,
                    }
                )
                continue

            num_tool_calls += 1
            result_text, results = execute_search_notes(block.input, embedder, store)
            sources.extend(results)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            )

        messages.append({"role": "user", "content": tool_results})

    # Iteration cap hit while Claude was still asking for more searches.
    # Force one final call with no tools available, so the model must
    # synthesize an answer from whatever it's already gathered rather than
    # the turn silently returning nothing.
    final_response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT
        + "\n\nYou have used your available searches for this turn. Answer "
        "now using only the passages already found above.",
        messages=messages,
        output_config={"effort": effort},
    )
    messages.append({"role": "assistant", "content": final_response.content})

    return AgentTurnResult(
        text=_extract_final_text(final_response),
        sources=_dedupe_sources(sources),
        messages=messages,
        num_tool_calls=num_tool_calls,
        stop_reason=final_response.stop_reason,
    )


def _extract_final_text(response) -> str:
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        explanation = getattr(details, "explanation", None) if details else None
        return explanation or "I'm not able to answer that."

    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts).strip()


def _dedupe_sources(sources: List[RetrievedChunk]) -> List[RetrievedChunk]:
    """The model may issue overlapping searches (a refined re-query often
    surfaces some of the same chunks as the first attempt) — keep the
    highest-scoring instance of each chunk rather than showing the same
    citation twice with two different scores.
    """
    best: dict = {}
    for chunk in sources:
        key = (chunk.course, chunk.topic, chunk.source_file, chunk.chunk_index)
        if key not in best or chunk.score > best[key].score:
            best[key] = chunk
    return sorted(best.values(), key=lambda c: c.score, reverse=True)
