"""Order item REST interface."""

from __future__ import annotations

from loom.rest.model import RestInterface, RestRoute

from app.order_item.model import OrderItem
from app.order_item.use_cases import (
    CreateOrderItemUseCase,
    DeleteOrderItemUseCase,
    GetOrderItemUseCase,
    ListOrderItemsUseCase,
    UpdateOrderItemUseCase,
)


class OrderItemRestInterface(RestInterface[OrderItem]):
    """REST interface for order items."""

    prefix = "/order-items"
    tags = ("OrderItems",)
    routes = (
        RestRoute(
            use_case=CreateOrderItemUseCase,
            method="POST",
            path="/",
            status_code=201,
            summary="Create order item",
            description="Add a product line to an existing order.",
        ),
        RestRoute(
            use_case=ListOrderItemsUseCase,
            method="GET",
            path="/",
            summary="List order items",
            description="List order items with filtering, sorting, and pagination.",
        ),
        RestRoute(
            use_case=GetOrderItemUseCase,
            method="GET",
            path="/{order_item_id}",
            summary="Get order item",
            description="Get an order item by id.",
        ),
        RestRoute(
            use_case=UpdateOrderItemUseCase,
            method="PATCH",
            path="/{order_item_id}",
            summary="Update order item",
            description="Partially update quantity or unit price.",
        ),
        RestRoute(
            use_case=DeleteOrderItemUseCase,
            method="DELETE",
            path="/{order_item_id}",
            summary="Delete order item",
            description="Delete an order item by id.",
        ),
    )
