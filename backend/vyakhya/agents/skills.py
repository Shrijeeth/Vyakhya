"""HyperFrames skills as Agno ``LocalSkills``.

Loads the vendored ``skills/`` directory (heygen-com/hyperframes, Apache-2.0)
as an Agno :class:`Skills` bundle. Attached to the visual-designer agent so it
can author HyperFrames-valid HTML using the same authoring contract the render
service enforces. Agno injects a skills system-prompt snippet and exposes
``get_skill_instructions`` / ``get_skill_reference`` / ``get_skill_script`` tools
the agent calls on demand.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from vyakhya.core.config import get_settings
from vyakhya.core.logging import get_logger

log = get_logger(__name__)

# Candidate skills/ locations: the repo root (local dev) and /app/skills (Docker
# image). backend/vyakhya/agents/skills.py → parents[3] == repo root.
_REPO_SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
_DOCKER_SKILLS_DIR = Path("/app/skills")


def skills_dir() -> Path:
    """Resolve the skills directory, tolerating an empty SKILLS_DIR override
    (e.g. an env_file line that shadows the image's ENV)."""
    configured = get_settings().skills_dir.strip()
    if configured and Path(configured).is_dir():
        return Path(configured)
    for candidate in (_REPO_SKILLS_DIR, _DOCKER_SKILLS_DIR):
        if candidate.is_dir():
            return candidate
    return _REPO_SKILLS_DIR


@lru_cache
def get_hyperframes_skills():  # noqa: ANN201 - agno.skills.Skills, imported lazily
    """Return the loaded HyperFrames Skills bundle (cached). Requires the
    ``agents`` extra (``uv sync --extra agents``)."""
    from agno.skills import LocalSkills, Skills

    path = skills_dir()
    skills = Skills(loaders=[LocalSkills(path=str(path), validate=False)])
    log.info("hyperframes skills loaded from %s: %s", path, skills.get_skill_names())
    return skills
