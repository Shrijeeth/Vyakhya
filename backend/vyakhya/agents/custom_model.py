"""OpenAILike wrapper for "custom" OpenAI-compatible endpoints.

With no options enabled this behaves exactly like a plain ``OpenAILike``.
Two per-connection options (set in Model Config when creating the
connection) adapt it to endpoints that deviate from the reference API:

- ``fold_system_prompt`` — some endpoints silently drop ``role:"system"``
  messages (substituting their own system prompt). Agno delivers agent
  instructions — and its JSON-mode schema directive — as a system message,
  so the model never sees the task contract. When enabled, every system
  message is folded into the first user message instead.

- ``tool_name_prefix`` — some endpoints rewrite tool/function names with a
  fixed prefix, so Agno can't match tool calls back to registered functions
  (breaks the designer's skill tools). When set, the prefix is stripped
  from response tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agno.models.message import Message
from agno.models.openai.like import OpenAILike

from vyakhya.core.logging import get_logger

log = get_logger(__name__)

_FOLD_TEMPLATE = "<instructions>\n{system}\n</instructions>\n\n"


def _fold_system_into_first_user(messages: list[Message]) -> list[Message]:
    """Move every system message's text into the first plain-string user
    message (or a synthetic head message) so a system-dropping endpoint still
    delivers the instructions."""
    sys_parts = [
        m.content
        for m in messages
        if m.role == "system" and isinstance(m.content, str) and m.content.strip()
    ]
    rest = [m for m in messages if m.role != "system"]
    if not sys_parts:
        return rest

    instructions = _FOLD_TEMPLATE.format(system="\n\n".join(sys_parts))
    for i, m in enumerate(rest):
        if m.role == "user" and isinstance(m.content, str):
            rest[i] = Message(role="user", content=f"{instructions}{m.content}")
            return rest
    rest.insert(0, Message(role="user", content=instructions.rstrip()))
    return rest


@dataclass
class CustomChatModel(OpenAILike):
    """OpenAILike for bring-your-own OpenAI-compatible endpoints."""

    fold_system_prompt: bool = field(default=False)
    tool_name_prefix: str = field(default="")

    def _prepare(self, messages: list[Message]) -> list[Message]:
        if not self.fold_system_prompt:
            return messages
        return _fold_system_into_first_user(messages)

    def _strip_prefix(self, fn: Any) -> None:
        p = self.tool_name_prefix
        if p and fn is not None and fn.name and fn.name.startswith(p):
            fn.name = fn.name[len(p) :]

    async def ainvoke(self, messages: list[Message], *args: Any, **kwargs: Any):  # noqa: ANN201
        return await super().ainvoke(self._prepare(messages), *args, **kwargs)

    def invoke(self, messages: list[Message], *args: Any, **kwargs: Any):  # noqa: ANN201
        return super().invoke(self._prepare(messages), *args, **kwargs)

    async def ainvoke_stream(self, messages: list[Message], *args: Any, **kwargs: Any):  # noqa: ANN201
        async for chunk in super().ainvoke_stream(self._prepare(messages), *args, **kwargs):
            yield chunk

    def invoke_stream(self, messages: list[Message], *args: Any, **kwargs: Any):  # noqa: ANN201
        yield from super().invoke_stream(self._prepare(messages), *args, **kwargs)

    def _parse_provider_response(self, response: Any, **kwargs: Any):  # noqa: ANN201
        if self.tool_name_prefix:
            choices = getattr(response, "choices", None) or []
            message = getattr(choices[0], "message", None) if choices else None
            for tc in (getattr(message, "tool_calls", None) if message else None) or []:
                self._strip_prefix(getattr(tc, "function", None))
        return super()._parse_provider_response(response, **kwargs)

    def _parse_provider_response_delta(self, response_delta: Any):  # noqa: ANN201
        if self.tool_name_prefix:
            choices = getattr(response_delta, "choices", None) or []
            delta = getattr(choices[0], "delta", None) if choices else None
            for tc in (getattr(delta, "tool_calls", None) if delta else None) or []:
                self._strip_prefix(getattr(tc, "function", None))
        return super()._parse_provider_response_delta(response_delta)
