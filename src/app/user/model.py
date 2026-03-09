"""User domain model."""

from __future__ import annotations

from loom.core.model import ColumnField, TimestampedModel


class User(TimestampedModel):
    """Store user."""

    __tablename__ = "users"

    id: int = ColumnField(primary_key=True, autoincrement=True)
    full_name: str = ColumnField(length=120)
    email: str = ColumnField(length=255, unique=True, index=True)
