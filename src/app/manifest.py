"""Manifest for dummy store app discovery."""

from __future__ import annotations

from app.address.interface import AddressRestInterface
from app.address.model import Address
from app.address.use_cases import (
    CreateAddressUseCase,
    DeleteAddressUseCase,
    GetAddressUseCase,
    ListAddressesUseCase,
    UpdateAddressUseCase,
)
from app.order.interface import OrderRestInterface
from app.order.model import Order
from app.order.use_cases import (
    CreateOrderUseCase,
    DeleteOrderUseCase,
    GetOrderUseCase,
    ListOrdersUseCase,
    UpdateOrderUseCase,
)
from app.order_item.interface import OrderItemRestInterface
from app.order_item.model import OrderItem
from app.order_item.use_cases import (
    CreateOrderItemUseCase,
    DeleteOrderItemUseCase,
    GetOrderItemUseCase,
    ListOrderItemsUseCase,
    UpdateOrderItemUseCase,
)
from app.product.callbacks import RestockEmailFailureCallback, RestockEmailSuccessCallback
from app.product.interface import ProductRestInterface
from app.product.jobs import BuildProductSummaryJob, SendRestockEmailJob, SyncProductToErpJob
from app.product.model import Product
from app.product.use_cases import (
    BuildProductSummaryUseCase,
    DispatchRestockEmailUseCase,
    ListLowStockProductsUseCase,
    RestockWorkflowUseCase,
    SyncProductsToErpUseCase,
)
from app.user.interface import UserRestInterface
from app.user.model import User

MODELS = [User, Address, Product, Order, OrderItem]
USE_CASES: list[type[object]] = [
    CreateAddressUseCase,
    GetAddressUseCase,
    ListAddressesUseCase,
    UpdateAddressUseCase,
    DeleteAddressUseCase,
    CreateOrderUseCase,
    GetOrderUseCase,
    ListOrdersUseCase,
    UpdateOrderUseCase,
    DeleteOrderUseCase,
    CreateOrderItemUseCase,
    GetOrderItemUseCase,
    ListOrderItemsUseCase,
    UpdateOrderItemUseCase,
    DeleteOrderItemUseCase,
    ListLowStockProductsUseCase,
    DispatchRestockEmailUseCase,
    BuildProductSummaryUseCase,
    RestockWorkflowUseCase,
    SyncProductsToErpUseCase,
]
JOBS: list[type[object]] = [
    SendRestockEmailJob,
    BuildProductSummaryJob,
    SyncProductToErpJob,
]
CALLBACKS: list[type[object]] = [
    RestockEmailSuccessCallback,
    RestockEmailFailureCallback,
]
INTERFACES = [
    UserRestInterface,
    AddressRestInterface,
    ProductRestInterface,
    OrderRestInterface,
    OrderItemRestInterface,
]
