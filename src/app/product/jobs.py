"""Background-like product jobs for store scenarios."""

from __future__ import annotations

from loom.core.command import Command
from loom.core.job.job import Job
from loom.core.use_case import Input, LoadById

from app.product.model import Product


class SendRestockEmailJobCommand(Command, frozen=True):
    product_id: int
    recipient_email: str
    force_fail: bool = False


class SyncProductToErpJobCommand(Command, frozen=True):
    product_id: int
    force_fail: bool = False


class SendRestockEmailJob(Job[bool]):
    """Simulate sending a restock notification email."""

    __queue__ = "notifications"

    async def execute(
        self,
        product_id: int,
        cmd: SendRestockEmailJobCommand = Input(),
        product: Product = LoadById(Product, by="product_id"),
    ) -> bool:
        if cmd.force_fail:
            raise RuntimeError("forced restock email failure")

        if product.stock > 0:
            return False

        _ = cmd.recipient_email
        return True


class BuildProductSummaryJob(Job[str]):
    """Build a simple human-readable product summary."""

    __queue__ = "analytics"

    async def execute(
        self,
        product_id: int,
        product: Product = LoadById(Product, by="product_id"),
    ) -> str:
        availability = "in stock" if product.stock > 0 else "out of stock"
        return (
            f"Product {product.sku} ({product.name}) in category {product.category} "
            f"costs {product.price_cents} cents and is {availability}."
        )


class SyncProductToErpJob(Job[bool]):
    """Simulate pushing a product to an external ERP."""

    __queue__ = "erp"

    async def execute(
        self,
        product_id: int,
        cmd: SyncProductToErpJobCommand = Input(),
        product: Product = LoadById(Product, by="product_id"),
    ) -> bool:
        if cmd.force_fail:
            raise RuntimeError(f"forced ERP sync failure for product {product_id}")

        _ = product
        return True
