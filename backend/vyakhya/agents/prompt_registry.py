"""Markdown prompt loader (one file per agent prompt, shopup-agents style)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class PromptNotFound(Exception): ...


@lru_cache
def get_prompt(name: str) -> str:
    """Return the prompt text of ``prompts/<name>.md`` (e.g. "planner-system")."""
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"invalid prompt name: {name}")
    path = _PROMPTS_DIR / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptNotFound(name) from exc
