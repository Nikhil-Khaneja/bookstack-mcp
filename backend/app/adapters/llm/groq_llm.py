"""Groq LLM adapter via langchain-groq.

Groq is used because (a) free tier, (b) OpenAI-compatible, (c) very low
latency — exactly what the interview bullet ("optimized backend for low-
latency AI-driven query workflows") needs to be defensible.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from ...core.config import get_settings
from ...core.logging import get_logger
from .base import ChatLLM, Message

log = get_logger(__name__)


class GroqLLM(ChatLLM):
    is_offline = False

    def __init__(self) -> None:
        s = get_settings()
        if not s.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self.name = s.groq_model
        self._client = ChatGroq(
            api_key=s.groq_api_key,
            model=s.groq_model,
            timeout=s.groq_timeout_s,
            max_retries=0,  # retries happen in the breaker wrapper
        )

    @staticmethod
    def _to_lc(messages: list[Message]) -> list:
        out = []
        for m in messages:
            if m.role == "system":
                out.append(SystemMessage(content=m.content))
            elif m.role == "assistant":
                out.append(AIMessage(content=m.content))
            else:
                out.append(HumanMessage(content=m.content))
        return out

    async def complete(
        self, messages: list[Message], *, json_mode: bool = False, temperature: float = 0.0
    ) -> str:
        client = self._client
        if json_mode:
            client = client.bind(response_format={"type": "json_object"}, temperature=temperature)
        else:
            client = client.bind(temperature=temperature)
        resp = await client.ainvoke(self._to_lc(messages))
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    async def stream(
        self, messages: list[Message], *, temperature: float = 0.4
    ) -> AsyncIterator[str]:
        client = self._client.bind(temperature=temperature)
        async for chunk in client.astream(self._to_lc(messages)):
            text = getattr(chunk, "content", "") or ""
            if text:
                yield text
