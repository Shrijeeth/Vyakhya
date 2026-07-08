"""Alembic target: `Base.metadata` with every model registered."""

from vyakhya.core.database import Base  # noqa: F401
from vyakhya.db import models  # noqa: F401  (imports all models onto the metadata)

metadata = Base.metadata
