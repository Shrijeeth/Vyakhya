"""Shared Pydantic base — camelCase on the wire, snake_case in Python.

Field names stay snake_case (so `from_attributes` reads ORM attributes directly)
while the JSON alias is camelCase (matching docs/api.md and the TS types).
FastAPI serializes responses by alias by default.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
