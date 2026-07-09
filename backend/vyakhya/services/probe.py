"""Provider connectivity probes.

Validate a provider connection (key + endpoint reachability) without spending
completion/TTS credits by hitting each provider's cheapest **authenticated**
endpoint — usually its model/voice list. A 2xx means the key is valid and the
endpoint is reachable. Never raises: always returns a :class:`ProbeResult` so
callers can render a clean success/failure card instead of a 500.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from vyakhya.core.logging import get_logger
from vyakhya.enums import KEYLESS_PROVIDERS, ProviderId

log = get_logger(__name__)

# Hard wall-clock cap so a hung provider doesn't block the UI button forever.
_TIMEOUT = 15.0

# Default API bases per provider (overridable per connection via base_url).
_DEFAULT_BASE: dict[ProviderId, str] = {
    ProviderId.OPENAI: "https://api.openai.com/v1",
    ProviderId.ANTHROPIC: "https://api.anthropic.com/v1",
    ProviderId.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
    ProviderId.GROQ: "https://api.groq.com/openai/v1",
    ProviderId.OLLAMA: "http://localhost:11434",
    ProviderId.ELEVENLABS: "https://api.elevenlabs.io/v1",
    ProviderId.DEEPGRAM: "https://api.deepgram.com/v1",
}


@dataclass
class ProbeResult:
    success: bool
    latency_ms: int
    detail: str | None = None
    error: str | None = None


def _request_spec(
    provider: ProviderId, base: str, api_key: str
) -> tuple[str, dict[str, str], dict[str, str] | None]:
    """Return (url, headers, params) for the provider's auth-check endpoint."""
    if provider in (ProviderId.OPENAI, ProviderId.GROQ):
        return f"{base}/models", {"Authorization": f"Bearer {api_key}"}, None
    if provider == ProviderId.ANTHROPIC:
        return (
            f"{base}/models",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            None,
        )
    if provider == ProviderId.GEMINI:
        return f"{base}/models", {}, {"key": api_key}
    if provider == ProviderId.OLLAMA:
        return f"{base}/api/tags", {}, None
    if provider == ProviderId.ELEVENLABS:
        return f"{base}/models", {"xi-api-key": api_key}, None
    if provider == ProviderId.DEEPGRAM:
        return f"{base}/projects", {"Authorization": f"Token {api_key}"}, None
    if provider in (ProviderId.CUSTOM, ProviderId.CUSTOM_TTS):
        return f"{base}/models", {"Authorization": f"Bearer {api_key}"}, None
    raise ValueError(f"no probe for provider {provider}")


async def probe_provider(
    provider: ProviderId, model: str, api_key: str, base_url: str | None = None
) -> ProbeResult:
    """Probe a provider's connectivity. Never raises."""
    started = time.monotonic()

    # Built-in engine needs no network.
    if provider == ProviderId.HYPERFRAMES:
        log.info("probe provider=hyperframes builtin=ok")
        return ProbeResult(success=True, latency_ms=0, detail="Built-in engine — always available")

    if provider in (ProviderId.CUSTOM, ProviderId.CUSTOM_TTS) and not base_url:
        return ProbeResult(success=False, latency_ms=0, error="Base URL required")
    if (
        provider not in KEYLESS_PROVIDERS
        and provider not in (ProviderId.CUSTOM, ProviderId.CUSTOM_TTS)
        and not api_key
    ):
        return ProbeResult(success=False, latency_ms=0, error="API key required")

    base = (base_url or _DEFAULT_BASE.get(provider, "")).rstrip("/")
    url, headers, params = _request_spec(provider, base, api_key)
    log.info("probe provider=%s model=%s url=%s", provider.value, model, url)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers, params=params)
        elapsed = int((time.monotonic() - started) * 1000)
        if resp.status_code < 400:
            log.info(
                "probe ok provider=%s status=%s ms=%s", provider.value, resp.status_code, elapsed
            )
            return ProbeResult(success=True, latency_ms=elapsed, detail=f"HTTP {resp.status_code}")
        log.warning(
            "probe failed provider=%s status=%s body=%s",
            provider.value,
            resp.status_code,
            resp.text[:200],
        )
        return ProbeResult(
            success=False,
            latency_ms=elapsed,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:  # noqa: BLE001 - report any failure as a clean result
        elapsed = int((time.monotonic() - started) * 1000)
        log.warning("probe error provider=%s err=%s", provider.value, exc)
        return ProbeResult(success=False, latency_ms=elapsed, error=f"{type(exc).__name__}: {exc}")
