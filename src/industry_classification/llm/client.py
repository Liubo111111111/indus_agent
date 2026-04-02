from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, prompt: str, payload: dict) -> str:
        """Return raw model output text."""

