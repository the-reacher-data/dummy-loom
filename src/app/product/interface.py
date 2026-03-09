"""Product REST interface."""

from __future__ import annotations

from loom.rest.autocrud import build_auto_routes
from loom.rest.model import PaginationMode, RestInterface, RestRoute

from app.product.model import Product
from app.product.use_cases import (
    BuildProductSummaryUseCase,
    DispatchRestockEmailUseCase,
    ListLowStockProductsUseCase,
    RestockWorkflowUseCase,
    SyncProductsToErpUseCase,
)


class ProductRestInterface(RestInterface[Product]):
    """REST interface for products."""

    prefix = "/products"
    tags = ("Products",)
    pagination_mode = PaginationMode.CURSOR
    routes = (
        RestRoute(
            use_case=ListLowStockProductsUseCase,
            method="GET",
            path="/low-stock",
            summary="List low stock products",
            description="Returns products with stock less than or equal to max_stock.",
        ),
        RestRoute(
            use_case=DispatchRestockEmailUseCase,
            method="POST",
            path="/{product_id}/jobs/restock-email",
            summary="Dispatch restock email job",
            description="Simulates sending a restock email for a product.",
            status_code=202,
        ),
        RestRoute(
            use_case=BuildProductSummaryUseCase,
            method="GET",
            path="/{product_id}/jobs/summary",
            summary="Build product summary",
            description="Runs a fake analytics job and returns the computed summary.",
        ),
        RestRoute(
            use_case=RestockWorkflowUseCase,
            method="POST",
            path="/{product_id}/workflows/restock",
            summary="Run restock workflow",
            description=(
                "Executes a use-case chain (summary + dispatch) and attaches "
                "success/failure callbacks to the restock job."
            ),
            status_code=202,
        ),
        RestRoute(
            use_case=SyncProductsToErpUseCase,
            method="POST",
            path="/jobs/sync-erp",
            summary="Dispatch ERP sync jobs",
            description="Dispatches fake ERP sync jobs for multiple products.",
            status_code=202,
        ),
        *build_auto_routes(Product, ()),
    )
