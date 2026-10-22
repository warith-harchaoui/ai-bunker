"""
Screening a streamed completion, without giving up streaming.

The problem, and why the old answer was too pessimistic
-------------------------------------------------------
Command screening is the one guarantee this project sells: a tool call is
refused *before it runs*, at a point no client can disable. Until now it did
not apply to `stream: true`, which is the mode every agent client uses by
default -- so the guarantee was off exactly where it was needed, and
`/health` said so.

The reason given was that a tool call arrives in fragments, so refusing one
would mean buffering the whole response and losing what streaming is for. The
first half is true. The second does not follow, and the reason is a fact about
clients rather than about protocols:

    **No client can act on half a tool call.**

A tool call is executed once it is complete; until then a client has nothing
to run. Content deltas are different -- those are shown to a human as they
arrive, and holding them back would be the real cost. So the split is clean:

* **content deltas pass through untouched**, token by token, as before;
* **tool-call deltas are held**, assembled, screened when the message ends,
  and only then released.

The user watches the answer appear exactly as before. What they do not see is
a refused command being handed to their client.

Why this assembles into the non-streaming shape
-----------------------------------------------
`as_response()` builds the same dictionary a non-streamed completion would
have produced, so `pipeline.apply_outbound` screens it unchanged. That reuse
is the point rather than a convenience: if the streamed path had its own
screening, `stream: true` and `stream: false` would be two enforcement
behaviours to keep in agreement, and they would eventually disagree. There is
one decision procedure, fed from two directions.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: The sentinel that ends a Server-Sent Events stream in the OpenAI protocol.
DONE = "[DONE]"


def parse(line: str) -> dict[str, Any] | None:
    """The JSON object in one `data:` line, or ``None``.

    ``None`` for a comment, a blank keep-alive, the `[DONE]` sentinel, and for
    anything that does not parse. The last one is deliberate: an upstream that
    emits a malformed chunk should degrade to "not screenable" and be passed
    through, not take the gateway down mid-answer.
    """
    if not line or not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if not payload or payload == DONE:
        return None
    try:
        parsed = json.loads(payload)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def carries_tool_call(chunk: dict[str, Any]) -> bool:
    """Whether this chunk carries any part of a tool call."""
    for choice in chunk.get("choices") or []:
        if (choice.get("delta") or {}).get("tool_calls"):
            return True
    return False


def finished(chunk: dict[str, Any]) -> bool:
    """Whether this chunk closes a choice, whatever the reason."""
    return any((choice.get("finish_reason") is not None) for choice in chunk.get("choices") or [])


@dataclass
class Assembler:
    """Reassembles the tool calls scattered across a streamed completion.

    The streamed shape gives an id and a function name once, then appends to
    ``function.arguments`` across however many chunks the engine felt like
    using. Indices, not positions, identify a call: an engine may interleave
    two calls and the index is the only thing that says which is which.
    """

    #: ``choice index -> tool-call index -> the call being assembled``.
    calls: dict[int, dict[int, dict[str, Any]]] = field(default_factory=dict)
    #: Chunks held back because they carried tool-call fragments.
    held: list[str] = field(default_factory=list)
    model: str = ""
    response_id: str = ""
    created: int = 0
    finish_reason: str = ""

    def feed(self, line: str) -> bool:
        """Take one raw SSE line. Returns ``True`` if it must be held back.

        A line is held when it carries tool-call data, because releasing it
        would hand the client a command the gateway has not judged yet.
        Everything else -- content, role, usage, keep-alives -- is released
        immediately, which is what keeps the answer streaming.
        """
        chunk = parse(line)
        if chunk is None:
            return False

        self.model = chunk.get("model") or self.model
        self.response_id = chunk.get("id") or self.response_id
        self.created = chunk.get("created") or self.created

        for choice in chunk.get("choices") or []:
            if choice.get("finish_reason") is not None:
                self.finish_reason = str(choice["finish_reason"])
            index = int(choice.get("index") or 0)
            for fragment in (choice.get("delta") or {}).get("tool_calls") or []:
                self._merge(index, fragment)

        if carries_tool_call(chunk):
            self.held.append(line)
            return True
        return False

    def _merge(self, choice_index: int, fragment: dict[str, Any]) -> None:
        """Fold one fragment into the call it belongs to."""
        slot = self.calls.setdefault(choice_index, {})
        index = int(fragment.get("index") or 0)
        call = slot.setdefault(index, {"id": "", "type": "function", "function": {}})

        if fragment.get("id"):
            call["id"] = fragment["id"]
        if fragment.get("type"):
            call["type"] = fragment["type"]

        function = fragment.get("function") or {}
        if function.get("name"):
            call["function"]["name"] = function["name"]
        if function.get("arguments"):
            # Concatenated, never replaced: the arguments are a JSON document
            # delivered in slices, and assigning would keep only the last one.
            call["function"]["arguments"] = (
                call["function"].get("arguments", "") + function["arguments"]
            )

    @property
    def has_calls(self) -> bool:
        return any(slot for slot in self.calls.values())

    def tool_calls(self, choice_index: int = 0) -> list[dict[str, Any]]:
        """The assembled calls for one choice, in the order the engine indexed
        them."""
        slot = self.calls.get(choice_index) or {}
        return [slot[i] for i in sorted(slot)]

    def as_response(self) -> dict[str, Any]:
        """The non-streamed completion this stream would have been.

        Built so `pipeline.apply_outbound` can screen it with no knowledge
        that a stream was involved -- one decision procedure, two ways in.
        """
        return {
            "id": self.response_id or "chatcmpl-stream",
            "object": "chat.completion",
            "created": self.created or 0,
            "model": self.model,
            "choices": [
                {
                    "index": index,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": self.tool_calls(index),
                    },
                    "finish_reason": self.finish_reason or "tool_calls",
                }
                for index in sorted(self.calls)
                if self.calls[index]
            ],
        }


def sse(payload: dict[str, Any]) -> str:
    """One Server-Sent Events frame."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def refusal_frames(assembler: Assembler, rule: Any, refusals: list[dict[str, Any]]) -> list[str]:
    """What a client receives instead of a refused command.

    Deliberately the same information the non-streamed path puts in its
    response: the tool calls stay, so the conversation remains well-formed,
    and the refusal travels beside them under ``ai_bunker``. A streamed
    refusal that invented its own shape would be a second thing for a client
    to understand, and the two would drift.
    """
    frames = [
        sse(
            {
                "id": assembler.response_id or "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": assembler.created or 0,
                "model": assembler.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                "ai_bunker": {
                    "refused_by": getattr(rule, "id", ""),
                    "reason": getattr(rule, "description", ""),
                    "refusals": refusals,
                },
            }
        )
    ]
    return frames
