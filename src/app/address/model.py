"""Address domain model."""

from __future__ import annotations

from loom.core.model import BaseModel, ColumnField, OnDelete


class Address(BaseModel):
    """User address."""

    __tablename__ = "addresses"

    id: int = ColumnField(primary_key=True, autoincrement=True)
    user_id: int = ColumnField(foreign_key="users.id", on_delete=OnDelete.CASCADE, index=True)
    label: str = ColumnField(length=80)
    street: str = ColumnField(length=255)
    city: str = ColumnField(length=120)
    country: str = ColumnField(length=120)
    zip_code: str = ColumnField(length=20)
