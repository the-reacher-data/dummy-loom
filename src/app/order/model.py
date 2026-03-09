"""Order domain model."""

from __future__ import annotations

from loom.core.model import ColumnField, TimestampedModel, OnDelete


class Order(TimestampedModel):
    """Order aggregate."""

    __tablename__ = "orders"

    id: int = ColumnField(primary_key=True, autoincrement=True)
    user_id: int = ColumnField(foreign_key="users.id", on_delete=OnDelete.CASCADE, index=True)
    address_id: int = ColumnField(foreign_key="addresses.id", on_delete=OnDelete.RESTRICT, index=True)
    status: str = ColumnField(length=40, default="created", index=True)
    payment_method: str = ColumnField(length=60, default="card")
