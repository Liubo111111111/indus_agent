from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import httpx

from industry_classification.settings import LLMSettings, load_llm_settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def complete(self, prompt: str, payload: dict) -> str:
        """Return raw model output text."""


class HttpLLMClient:
    """通过 OpenAI 兼容 HTTP 接口调用 LLM。"""

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self._settings = settings or load_llm_settings()
        if not self._settings.api_key:
            raise ValueError(
                "LLM API key not configured. "
                "Set DASHSCOPE_API_KEY, OPENAI_API_KEY, or LLM_API_KEY in .env"
            )
        if not self._settings.base_url:
            raise ValueError(
                "LLM base URL not configured. "
                "Set LLM_BASE_URL, DASHSCOPE_BASE_URL, or OPENAI_BASE_URL in .env"
            )
        self._client = httpx.Client(
            timeout=httpx.Timeout(self._settings.timeout_sec, connect=10.0),
        )

    def complete(self, prompt: str, payload: dict) -> str:
        """发送 prompt 到 LLM，返回原始文本输出。"""
        messages = self._build_messages(prompt)
        last_error: Exception | None = None

        for attempt in range(self._settings.max_retry + 1):
            try:
                response = self._call_api(messages)
                text = self._extract_text(response)
                logger.debug(
                    "llm_complete ok attempt=%d model=%s chars=%d",
                    attempt, self._settings.model, len(text),
                )
                return text
            except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                last_error = exc
                wait = min(2 ** attempt, 8)
                logger.warning(
                    "llm_complete retry attempt=%d error=%s wait=%ds",
                    attempt, type(exc).__name__, wait,
                )
                time.sleep(wait)
            except Exception as exc:
                raise RuntimeError(f"llm_call_failed: {exc}") from exc

        raise RuntimeError(
            f"llm_call_exhausted_retries after {self._settings.max_retry + 1} attempts: {last_error}"
        )

    def _build_messages(self, prompt: str) -> list[dict[str, str]]:
        parts = prompt.split("[USER]\n", maxsplit=1)
        if len(parts) == 2:
            system_part = parts[0]
            user_part = parts[1]
            system_text = system_part.replace("[TASK:", "").split("]\n", 1)[-1]
            system_text = system_text.replace("[SYSTEM]\n", "").strip()
            return [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_part.strip()},
            ]
        return [{"role": "user", "content": prompt}]

    def _call_api(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        body = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }
        resp = self._client.post(
            self._settings.base_url,
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        choices = response.get("choices", [])
        if not choices:
            raise ValueError("llm_response_no_choices")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise ValueError("llm_response_empty_content")
        return content

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpLLMClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
