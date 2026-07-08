"""Unit tests for provider connectivity probes (no real network)."""

from __future__ import annotations

import httpx

from vyakhya.enums import KEYLESS_PROVIDERS, ProviderId, ProviderKind, provider_kind
from vyakhya.services import probe as probe_mod
from vyakhya.services.probe import ProbeResult, probe_provider


def test_provider_kind_mapping():
    assert provider_kind(ProviderId.OPENAI) is ProviderKind.LLM
    assert provider_kind(ProviderId.OLLAMA) is ProviderKind.LLM
    assert provider_kind(ProviderId.ELEVENLABS) is ProviderKind.TTS
    assert provider_kind(ProviderId.DEEPGRAM) is ProviderKind.TTS
    assert provider_kind(ProviderId.HYPERFRAMES) is ProviderKind.TTS


def test_keyless_set():
    assert ProviderId.OLLAMA in KEYLESS_PROVIDERS
    assert ProviderId.HYPERFRAMES in KEYLESS_PROVIDERS
    assert ProviderId.OPENAI not in KEYLESS_PROVIDERS


async def test_hyperframes_builtin_always_ok():
    r = await probe_provider(ProviderId.HYPERFRAMES, "builtin", "")
    assert r.success is True
    assert r.latency_ms == 0


async def test_missing_key_fails_without_network():
    r = await probe_provider(ProviderId.OPENAI, "gpt-5.5", "")
    assert r.success is False
    assert r.error == "API key required"


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Stand-in for httpx.AsyncClient that returns a canned response."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[tuple[str, dict, dict | None]] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str, headers: dict, params: dict | None) -> _FakeResponse:
        self.calls.append((url, headers, params))
        return self._response


async def test_success_path(monkeypatch):
    fake = _FakeClient(_FakeResponse(200, "ok"))
    monkeypatch.setattr(probe_mod.httpx, "AsyncClient", lambda **_: fake)
    r = await probe_provider(ProviderId.OPENAI, "gpt-5.5", "sk-test")
    assert r.success is True
    assert r.detail == "HTTP 200"
    # Correct OpenAI auth-check endpoint + bearer header.
    url, headers, _ = fake.calls[0]
    assert url.endswith("/models")
    assert headers["Authorization"] == "Bearer sk-test"


async def test_auth_failure_path(monkeypatch):
    fake = _FakeClient(_FakeResponse(401, "invalid key"))
    monkeypatch.setattr(probe_mod.httpx, "AsyncClient", lambda **_: fake)
    r = await probe_provider(ProviderId.ANTHROPIC, "claude-opus-4-8", "bad")
    assert r.success is False
    assert "401" in (r.error or "")


async def test_network_error_returns_clean_result(monkeypatch):
    def _boom(**_: object) -> None:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(probe_mod.httpx, "AsyncClient", _boom)
    r = await probe_provider(ProviderId.GROQ, "llama-3.3-70b-versatile", "k")
    assert isinstance(r, ProbeResult)
    assert r.success is False
    assert "ConnectError" in (r.error or "")


async def test_ollama_keyless_uses_tags(monkeypatch):
    fake = _FakeClient(_FakeResponse(200, "{}"))
    monkeypatch.setattr(probe_mod.httpx, "AsyncClient", lambda **_: fake)
    r = await probe_provider(ProviderId.OLLAMA, "qwen3:30b", "")
    assert r.success is True
    url, _, _ = fake.calls[0]
    assert url.endswith("/api/tags")
