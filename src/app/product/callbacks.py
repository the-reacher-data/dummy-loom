"""Job callbacks for product workflows."""

from __future__ import annotations

from typing import Any

from loom.core.use_case.invoker import ApplicationInvoker

from app.product.model import Product


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _append_suffix(category: str, suffix: str) -> str:
    token = f"-{suffix}"
    if category.endswith(token):
        return category
    return f"{category}{token}"


class RestockEmailSuccessCallback:
    """Callback that tags products when restock emails are sent successfully."""

    def __init__(self, app: ApplicationInvoker) -> None:
        self._app = app

    async def on_success(self, job_id: str, result: Any, **context: Any) -> None:
        if not bool(result):
            return
        _ = job_id
        await _apply_category_suffix(self._app, context=context, suffix="restock-notified")

    def on_failure(self, job_id: str, exc_type: str, exc_msg: str, **context: Any) -> None:
        _ = (job_id, exc_type, exc_msg, context)


class RestockEmailFailureCallback:
    """Callback that tags products when restock email dispatch fails."""

    def __init__(self, app: ApplicationInvoker) -> None:
        self._app = app

    def on_success(self, job_id: str, result: Any, **context: Any) -> None:
        _ = (job_id, result, context)

    async def on_failure(
        self,
        job_id: str,
        exc_type: str,
        exc_msg: str,
        **context: Any,
    ) -> None:
        _ = (job_id, exc_type, exc_msg)
        await _apply_category_suffix(self._app, context=context, suffix="restock-failed")


async def _apply_category_suffix(
    app: ApplicationInvoker,
    *,
    context: dict[str, Any],
    suffix: str,
) -> None:
    product_id = _as_int(context.get("product_id"))
    if product_id is None:
        return

    entity = app.entity(Product)
    loaded = await entity.get(params={"id": product_id})
    if loaded is None:
        return
    next_category = _append_suffix(loaded.category, suffix)
    if next_category == loaded.category:
        return
    await entity.update(
        params={"id": product_id},
        payload={"category": next_category},
    )
