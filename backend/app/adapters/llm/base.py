"""LLM protocol. One interface, multiple implementations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(slots=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@runtime_checkable
class ChatLLM(Protocol):
    name: str
    is_offline: bool

    async def complete(
        self, messages: list[Message], *, json_mode: bool = False, temperature: float = 0.0
    ) -> str: ...

    async def stream(
        self, messages: list[Message], *, temperature: float = 0.4
    ) -> AsyncIterator[str]: ...
