"""Build an Agno model from a stored provider connection.

Maps a Vyakhya ``ProviderId`` + model id + (decrypted) key onto the matching
Agno model class. LLM providers only — TTS providers (elevenlabs/deepgram/
hyperframes) are handled by the narration step, not an Agno LLM. Requires the
``agents`` extra.
"""

from __future__ import annotations

from typing import Any

from vyakhya.core.logging import get_logger
from vyakhya.enums import ProviderId

log = get_logger(__name__)

_GROQ_DEFAULT_BASE = "https://api.groq.com/openai/v1"
_OLLAMA_DEFAULT_HOST = "http://localhost:11434"


def build_llm_model(
    provider: ProviderId,
    model_id: str,
    api_key: str,
    base_url: str | None = None,
    settings: dict | None = None,
) -> Any:
    """Return an Agno ``Model`` for an LLM provider connection."""
    from agno.models.anthropic import Claude
    from agno.models.google import Gemini
    from agno.models.ollama import Ollama
    from agno.models.openai import OpenAIChat
    from agno.models.openai.like import OpenAILike

    log.info("building agno model provider=%s model=%s", provider.value, model_id)

    if provider == ProviderId.OPENAI:
        return OpenAIChat(id=model_id, api_key=api_key, base_url=base_url or None)
    if provider == ProviderId.ANTHROPIC:
        return Claude(id=model_id, api_key=api_key)
    if provider == ProviderId.GEMINI:
        return Gemini(id=model_id, api_key=api_key)
    if provider == ProviderId.GROQ:
        # Groq is OpenAI-compatible → OpenAILike with the Groq base.
        return OpenAILike(id=model_id, api_key=api_key, base_url=base_url or _GROQ_DEFAULT_BASE)
    if provider == ProviderId.OLLAMA:
        return Ollama(id=model_id, host=base_url or _OLLAMA_DEFAULT_HOST)
    if provider == ProviderId.CUSTOM:
        # Bring-your-own OpenAI-compatible endpoint (vLLM, LiteLLM,
        # OpenRouter, self-hosted gateways…). With no options set this is a
        # plain OpenAILike. The per-connection options (Model Config) adapt
        # it to non-reference endpoints: folding system messages into the
        # first user message and stripping a rewritten tool-name prefix.
        # When such compatibility options are on, structured output also
        # switches to agno's prompt-based JSON path — those endpoints tend
        # to accept `response_format: json_schema` without enforcing it.
        from vyakhya.agents.custom_model import CustomChatModel

        if not base_url:
            raise ValueError("custom LLM provider requires a base URL")
        opts = settings or {}
        fold = bool(opts.get("foldSystemPrompt", False))
        prefix = str(opts.get("toolNamePrefix", "") or "")
        model = CustomChatModel(
            id=model_id,
            api_key=api_key or "none",
            base_url=base_url,
            fold_system_prompt=fold,
            tool_name_prefix=prefix,
        )
        if fold or prefix:
            model.supports_native_structured_outputs = False
            model.supports_json_schema_outputs = False
        return model

    raise ValueError(f"{provider.value} is not an LLM provider (cannot build an Agno model)")
