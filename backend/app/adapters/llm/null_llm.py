"""Offline extractive LLM.

When GROQ_API_KEY isn't set we still want the pipeline to run end-to-end
so demos, CI, and the eval harness work without the internet. This
adapter returns deterministic outputs derived from the messages:

- For analyzer-style JSON requests, emit a minimal valid JSON.
- For writer streaming, echo the first retrieved chunk verbatim
  (caller is responsible for embedding the chunks in the prompt).

The audit trail clearly marks any response produced here as offline-
extractive so nothing is passed off as "generated".
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from .base import ChatLLM, Message


def _last_user(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""


class NullLLM(ChatLLM):
    name = "offline-extractive"
    is_offline = True

    async def complete(
        self, messages: list[Message], *, json_mode: bool = False, temperature: float = 0.0
    ) -> str:
        text = _last_user(messages)
        if json_mode:
            # Minimal analyzer-shaped JSON. Writer node won't hit this path with
            # json_mode because streaming is used for writing.
            return json.dumps(
                {
                    "summary": (text[:280] + "…") if len(text) > 280 else text,
                    "relevance_rationale": "offline extractive fallback",
                    "self_confidence": 0.2,
                }
            )
        return "[offline-extractive] " + text[:512]

    async def stream(
        self, messages: list[Message], *, temperature: float = 0.4
    ) -> AsyncIterator[str]:
        text = "[offline-extractive] " + _last_user(messages)[:512]
        # Chunk by ~20-char bursts so the UI sees real streaming behavior.
        for i in range(0, len(text), 20):
            yield text[i : i + 20]
