from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str


class LLMProvider(ABC):
    """Vendor-neutral text-generation boundary."""

    @abstractmethod
    async def generate(self, messages: list[LLMMessage]) -> LLMResponse:
        """Generate a response for an ordered conversation."""
