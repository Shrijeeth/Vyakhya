"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
