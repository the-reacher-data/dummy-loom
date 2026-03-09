"""Order REST interface."""

from __future__ import annotations

from loom.rest.model import PaginationMode, RestInterface, RestRoute

from app.order.model import Order
from app.order.use_cases import (
    CreateOrderUseCase,
    DeleteOrderUseCase,
    GetOrderUseCase,
    ListOrdersUseCase,
    UpdateOrderUseCase,
)


class OrderRestInterface(RestInterface[Order]):
    """REST interface for orders."""

    prefix = "/orders"
    tags = ("Orders",)
    pagination_mode = PaginationMode.OFFSET
    routes = (
        RestRoute(
            use_case=CreateOrderUseCase,
            method="POST",
            path="/",
            status_code=201,
            summary="Create order",
            description="Create a new order for an existing user and address.",
        ),
        RestRoute(
            use_case=ListOrdersUseCase,
            method="GET",
            path="/",
            summary="List orders",
            description="List orders with filtering, sorting, and pagination.",
        ),
        RestRoute(
            use_case=GetOrderUseCase,
            method="GET",
            path="/{order_id}",
            summary="Get order",
            description="Get an order by id.",
        ),
        RestRoute(
            use_case=UpdateOrderUseCase,
            method="PATCH",
            path="/{order_id}",
            summary="Update order",
            description="Partially update order status or payment method.",
        ),
        RestRoute(
            use_case=DeleteOrderUseCase,
            method="DELETE",
            path="/{order_id}",
            summary="Delete order",
            description="Delete an order by id.",
        ),
    )
