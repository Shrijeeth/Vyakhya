"""Import every model so `Base.metadata` is complete for Alembic autogenerate."""

from vyakhya.db.models.config import (  # noqa: F401
    AgentModelAssignment,
    AgentPrompt,
    InstallMeta,
    ProviderConnection,
)
from vyakhya.db.models.pipeline import (  # noqa: F401
    AgentNodeState,
    PipelineEvent,
    PipelineRun,
    VerifierFlag,
)
from vyakhya.db.models.project import Project, Scene, SceneCitation  # noqa: F401
from vyakhya.db.models.render import RenderJob, RenderSettings  # noqa: F401

__all__ = [
    "Project",
    "Scene",
    "SceneCitation",
    "PipelineRun",
    "AgentNodeState",
    "PipelineEvent",
    "VerifierFlag",
    "ProviderConnection",
    "AgentModelAssignment",
    "AgentPrompt",
    "InstallMeta",
    "RenderSettings",
    "RenderJob",
]
