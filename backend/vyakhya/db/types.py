"""Shared SQLAlchemy column-type helpers."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import Enum as SAEnum


def pg_enum(py_enum: type[Enum], name: str) -> SAEnum:
    """A native Postgres ENUM whose stored values are the enum *values*
    (the wire strings), not the Python member names.
    """
    return SAEnum(
        py_enum,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )
