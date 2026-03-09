"""Custom product use cases."""

from __future__ import annotations

from loom.core.command import Command
from loom.core.job.service import JobService
from loom.core.use_case.invoker import ApplicationInvoker
from loom.core.repository.abc.query import (
    FilterGroup,
    FilterOp,
    FilterSpec,
    PageResult,
    PaginationMode,
    QuerySpec,
    SortSpec,
)
from loom.core.use_case import F, Input, Rule
from loom.core.use_case.use_case import UseCase

from app.product.callbacks import RestockEmailFailureCallback, RestockEmailSuccessCallback
from app.product.jobs import BuildProductSummaryJob, SendRestockEmailJob, SyncProductToErpJob
from app.product.model import Product


class DispatchRestockEmailCommand(Command, frozen=True):
    recipient_email: str
    force_fail: bool = False


class DispatchRestockEmailResponse(Command, frozen=True):
    job_id: str
    queue: str


class ProductSummaryResponse(Command, frozen=True):
    product_id: int
    summary: str


class SyncProductsCommand(Command, frozen=True):
    product_ids: list[int]
    force_fail_ids: list[int] = []


class SyncProductsResponse(Command, frozen=True):
    dispatched: int
    job_ids: list[str]


class RestockWorkflowResponse(Command, frozen=True):
    summary: str
    restock_job_id: str
    queue: str


def _product_ids_must_not_be_empty(product_ids: list[int]) -> str | None:
    if product_ids:
        return None
    return "product_ids must include at least one product"


SYNC_PRODUCT_IDS_RULE = Rule.check(
    F(SyncProductsCommand).product_ids,
    via=_product_ids_must_not_be_empty,
)


class ListLowStockProductsUseCase(UseCase[Product, PageResult[Product]]):
    """List products considered low stock, sorted by stock and id."""

    async def execute(
        self,
        profile: str = "default",
    ) -> PageResult[Product]:
        max_stock = 5
        effective_limit = 20
        query = QuerySpec(
            filters=FilterGroup(
                filters=(
                    FilterSpec(field="stock", op=FilterOp.LTE, value=max_stock),
                )
            ),
            sort=(
                SortSpec(field="stock", direction="ASC"),
                SortSpec(field="id", direction="ASC"),
            ),
            pagination=PaginationMode.OFFSET,
            limit=effective_limit,
            page=1,
        )
        result = await self.main_repo.list_with_query(query, profile=profile)
        if not isinstance(result, PageResult):
            raise RuntimeError("Expected offset pagination result for low-stock query")
        return result


class DispatchRestockEmailUseCase(UseCase[Product, DispatchRestockEmailResponse]):
    """Dispatch a fake restock email job."""

    def __init__(self, job_service: JobService) -> None:
        self._jobs = job_service

    async def execute(
        self,
        product_id: str,
        cmd: DispatchRestockEmailCommand = Input(),
    ) -> DispatchRestockEmailResponse:
        product_id_int = int(product_id)
        handle = self._jobs.dispatch(
            SendRestockEmailJob,
            params={"product_id": product_id_int},
            payload={
                "product_id": product_id_int,
                "recipient_email": cmd.recipient_email,
                "force_fail": cmd.force_fail,
            },
            on_success=RestockEmailSuccessCallback,
            on_failure=RestockEmailFailureCallback,
        )
        return DispatchRestockEmailResponse(job_id=handle.job_id, queue=handle.queue)


class BuildProductSummaryUseCase(UseCase[Product, ProductSummaryResponse]):
    """Run a fake analytics job inline and return its output."""

    def __init__(self, job_service: JobService) -> None:
        self._jobs = job_service

    async def execute(self, product_id: str) -> ProductSummaryResponse:
        product_id_int = int(product_id)
        summary = await self._jobs.run(
            BuildProductSummaryJob,
            params={"product_id": product_id_int},
        )
        return ProductSummaryResponse(product_id=product_id_int, summary=summary)


class RestockWorkflowUseCase(UseCase[Product, RestockWorkflowResponse]):
    """Chain a use case and a callback-enabled job dispatch."""

    def __init__(self, app: ApplicationInvoker, job_service: JobService) -> None:
        self._app = app
        self._jobs = job_service

    async def execute(
        self,
        product_id: str,
        cmd: DispatchRestockEmailCommand = Input(),
    ) -> RestockWorkflowResponse:
        product_id_int = int(product_id)
        summary_result = await self._app.invoke(
            BuildProductSummaryUseCase,
            params={"product_id": product_id_int},
        )
        summary_text = summary_result.summary

        handle = self._jobs.dispatch(
            SendRestockEmailJob,
            params={"product_id": product_id_int},
            payload={
                "product_id": product_id_int,
                "recipient_email": cmd.recipient_email,
                "force_fail": cmd.force_fail,
            },
            on_success=RestockEmailSuccessCallback,
            on_failure=RestockEmailFailureCallback,
        )

        return RestockWorkflowResponse(
            summary=summary_text,
            restock_job_id=handle.job_id,
            queue=handle.queue,
        )


class SyncProductsToErpUseCase(UseCase[Product, SyncProductsResponse]):
    """Dispatch fake ERP sync jobs for a batch of products."""

    rules = [SYNC_PRODUCT_IDS_RULE]

    def __init__(self, job_service: JobService) -> None:
        self._jobs = job_service

    async def execute(self, cmd: SyncProductsCommand = Input()) -> SyncProductsResponse:
        fail_ids = set(cmd.force_fail_ids)
        handles = []
        for product_id in cmd.product_ids:
            handle = self._jobs.dispatch(
                SyncProductToErpJob,
                params={"product_id": product_id},
                payload={
                    "product_id": product_id,
                    "force_fail": product_id in fail_ids,
                },
            )
            handles.append(handle)

        return SyncProductsResponse(
            dispatched=len(handles),
            job_ids=[handle.job_id for handle in handles],
        )
