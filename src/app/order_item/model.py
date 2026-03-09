"""Order item domain model."""

from __future__ import annotations

from loom.core.model import BaseModel, ColumnField, OnDelete


class OrderItem(BaseModel):
    """Order line item."""

    __tablename__ = "order_items"

    id: int = ColumnField(primary_key=True, autoincrement=True)
    order_id: int = ColumnField(foreign_key="orders.id", on_delete=OnDelete.CASCADE, index=True)
    product_id: int = ColumnField(foreign_key="products.id", on_delete=OnDelete.RESTRICT, index=True)
    quantity: int = ColumnField()
    unit_price_cents: int = ColumnField()
