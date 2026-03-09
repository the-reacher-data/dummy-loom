"""Product domain model."""

from __future__ import annotations

from loom.core.model import ColumnField, TimestampedModel


class Product(TimestampedModel):
    """Catalog product."""

    __tablename__ = "products"

    id: int = ColumnField(primary_key=True, autoincrement=True)
    sku: str = ColumnField(length=64, unique=True, index=True)
    name: str = ColumnField(length=150)
    category: str = ColumnField(length=120, index=True)
    price_cents: int = ColumnField()
    stock: int = ColumnField()
