import pytest
import httpx

from industry_classification.llm import client as client_module
from industry_classification.llm.client import HttpLLMClient
from industry_classification.settings import LLMSettings


def _make_client(transport: httpx.BaseTransport, max_retry: int = 2) -> HttpLLMClient:
    client = HttpLLMClient(
        settings=LLMSettings(
            api_key="test-key",
            base_url="https://example.com/v1/chat/completions",
            model="test-model",
            timeout_sec=30,
            max_retry=max_retry,
        )
    )
    client._client.close()
    client._client = httpx.Client(transport=transport)
    return client


def test_complete_surfaces_403_details_without_retrying():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(403, text="RBAC: access denied", request=request)

    client = _make_client(httpx.MockTransport(handler), max_retry=2)

    with pytest.raises(RuntimeError, match="403.*RBAC: access denied"):
        client.complete("Reply with OK only.", {})

    assert calls["count"] == 1


def test_http_llm_client_disables_environment_proxy_settings(monkeypatch):
    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr(client_module.httpx, "Client", DummyClient)

    client = HttpLLMClient(
        settings=LLMSettings(
            api_key="test-key",
            base_url="https://example.com/v1/chat/completions",
            model="test-model",
            timeout_sec=30,
            max_retry=2,
        )
    )
    client.close()

    assert captured["trust_env"] is False
