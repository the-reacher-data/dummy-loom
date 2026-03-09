"""Order use cases with dependency and rule checks."""

from __future__ import annotations

from loom.core.command import Command, Patch
from loom.core.errors import NotFound
from loom.core.repository.abc.query import CursorResult, PageResult, QuerySpec
from loom.core.use_case import Exists, F, Input, OnMissing, Rule
from loom.core.use_case.use_case import UseCase

from app.address.model import Address
from app.order.model import Order
from app.user.model import User

_ALLOWED_ORDER_STATUS = frozenset({"created", "paid", "cancelled", "shipped"})


class CreateOrder(Command, frozen=True):
    user_id: int
    address_id: int
    status: str = "created"
    payment_method: str = "card"


class UpdateOrder(Command, frozen=True):
    status: Patch[str] = None
    payment_method: Patch[str] = None


def _status_must_be_supported(status: str) -> str | None:
    if status in _ALLOWED_ORDER_STATUS:
        return None
    return f"status must be one of: {', '.join(sorted(_ALLOWED_ORDER_STATUS))}"


CREATE_STATUS_RULE = Rule.check(F(CreateOrder).status, via=_status_must_be_supported)
UPDATE_STATUS_RULE = Rule.check(F(UpdateOrder).status, via=_status_must_be_supported).when_present(
    F(UpdateOrder).status
)


class CreateOrderUseCase(UseCase[Order, Order]):
    rules = [CREATE_STATUS_RULE]

    async def execute(
        self,
        cmd: CreateOrder = Input(),
        _user_exists: bool = Exists(User, from_command="user_id", against="id", on_missing=OnMissing.RAISE),
        _address_exists: bool = Exists(Address, from_command="address_id", against="id", on_missing=OnMissing.RAISE),
    ) -> Order:
        return await self.main_repo.create(cmd)


class GetOrderUseCase(UseCase[Order, Order]):
    async def execute(self, order_id: int, profile: str = "default") -> Order:
        order = await self.main_repo.get_by_id(order_id, profile=profile)
        if order is None:
            raise NotFound("Order", id=order_id)
        return order


class ListOrdersUseCase(UseCase[Order, PageResult[Order] | CursorResult[Order]]):
    async def execute(
        self,
        query: QuerySpec,
        profile: str = "default",
    ) -> PageResult[Order] | CursorResult[Order]:
        return await self.main_repo.list_with_query(query, profile=profile)


class UpdateOrderUseCase(UseCase[Order, Order]):
    rules = [UPDATE_STATUS_RULE]

    async def execute(self, order_id: int, cmd: UpdateOrder = Input()) -> Order:
        updated = await self.main_repo.update(order_id, cmd)
        if updated is None:
            raise NotFound("Order", id=order_id)
        return updated


class DeleteOrderUseCase(UseCase[Order, bool]):
    async def execute(self, order_id: int) -> bool:
        return await self.main_repo.delete(order_id)
