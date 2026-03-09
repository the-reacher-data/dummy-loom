"""Order item use cases with dependency and quantity checks."""

from __future__ import annotations

from loom.core.command import Command, Patch
from loom.core.errors import NotFound
from loom.core.repository.abc.query import CursorResult, PageResult, QuerySpec
from loom.core.use_case import Exists, F, Input, OnMissing, Rule
from loom.core.use_case.use_case import UseCase

from app.order.model import Order
from app.order_item.model import OrderItem
from app.product.model import Product


class CreateOrderItem(Command, frozen=True):
    order_id: int
    product_id: int
    quantity: int
    unit_price_cents: int


class UpdateOrderItem(Command, frozen=True):
    quantity: Patch[int] = None
    unit_price_cents: Patch[int] = None


def _quantity_must_be_positive(quantity: int) -> str | None:
    if quantity > 0:
        return None
    return "quantity must be greater than zero"


def _unit_price_must_not_be_negative(unit_price_cents: int) -> str | None:
    if unit_price_cents >= 0:
        return None
    return "unit_price_cents must be zero or positive"


CREATE_QUANTITY_RULE = Rule.check(F(CreateOrderItem).quantity, via=_quantity_must_be_positive)
UPDATE_QUANTITY_RULE = Rule.check(F(UpdateOrderItem).quantity, via=_quantity_must_be_positive).when_present(
    F(UpdateOrderItem).quantity
)
CREATE_UNIT_PRICE_RULE = Rule.check(F(CreateOrderItem).unit_price_cents, via=_unit_price_must_not_be_negative)
UPDATE_UNIT_PRICE_RULE = Rule.check(
    F(UpdateOrderItem).unit_price_cents,
    via=_unit_price_must_not_be_negative,
).when_present(F(UpdateOrderItem).unit_price_cents)


class CreateOrderItemUseCase(UseCase[OrderItem, OrderItem]):
    rules = [CREATE_QUANTITY_RULE, CREATE_UNIT_PRICE_RULE]

    async def execute(
        self,
        cmd: CreateOrderItem = Input(),
        _order_exists: bool = Exists(Order, from_command="order_id", against="id", on_missing=OnMissing.RAISE),
        _product_exists: bool = Exists(Product, from_command="product_id", against="id", on_missing=OnMissing.RAISE),
    ) -> OrderItem:
        return await self.main_repo.create(cmd)


class GetOrderItemUseCase(UseCase[OrderItem, OrderItem]):
    async def execute(self, order_item_id: int, profile: str = "default") -> OrderItem:
        order_item = await self.main_repo.get_by_id(order_item_id, profile=profile)
        if order_item is None:
            raise NotFound("OrderItem", id=order_item_id)
        return order_item


class ListOrderItemsUseCase(UseCase[OrderItem, PageResult[OrderItem] | CursorResult[OrderItem]]):
    async def execute(
        self,
        query: QuerySpec,
        profile: str = "default",
    ) -> PageResult[OrderItem] | CursorResult[OrderItem]:
        return await self.main_repo.list_with_query(query, profile=profile)


class UpdateOrderItemUseCase(UseCase[OrderItem, OrderItem]):
    rules = [UPDATE_QUANTITY_RULE, UPDATE_UNIT_PRICE_RULE]

    async def execute(self, order_item_id: int, cmd: UpdateOrderItem = Input()) -> OrderItem:
        updated = await self.main_repo.update(order_item_id, cmd)
        if updated is None:
            raise NotFound("OrderItem", id=order_item_id)
        return updated


class DeleteOrderItemUseCase(UseCase[OrderItem, bool]):
    async def execute(self, order_item_id: int) -> bool:
        return await self.main_repo.delete(order_item_id)
