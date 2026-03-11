"""Loom benchmark components discovered via manifest."""


import asyncio
import os
from typing import Any

from loom.core.command import Command
from loom.core.errors import NotFound
from loom.core.model import (
    Cardinality,
    ColumnField,
    ProjectionField,
    RelationField,
    TimestampedModel,
)
from loom.core.projection.loaders import CountLoader, ExistsLoader, JoinFieldsLoader
from loom.core.repository.abc import RepoFor
from loom.core.repository.abc.query import CursorResult, PageResult, QuerySpec
from loom.core.response import Response
from loom.core.use_case import Compute, F, Input, Rule
from loom.core.use_case.use_case import UseCase
from loom.rest.model import PaginationMode, RestInterface, RestRoute

_TABLE_PREFIX = os.getenv("BENCH_TABLE_PREFIX", "bench")
_TABLE_USERS = f"{_TABLE_PREFIX}_users"
_TABLE_RECORDS = f"{_TABLE_PREFIX}_records"
_TABLE_NOTES = f"{_TABLE_PREFIX}_notes"

_COUNTRY_TAX_RATES: dict[str, float] = {
    "US": 0.08,
    "ES": 0.21,
    "DE": 0.19,
    "FR": 0.20,
}
_COUPON_BONUS_DISCOUNT: dict[str, float] = {
    "VIP5": 5.0,
    "WELCOME10": 10.0,
    "SHIPFREE": 0.0,
}


class BenchUser(TimestampedModel):
    """Synthetic owner for benchmark records."""

    __tablename__ = _TABLE_USERS

    id: int = ColumnField(primary_key=True, autoincrement=True)
    name: str = ColumnField(length=120)
    email: str = ColumnField(length=255, unique=True, index=True)


class BenchNote(TimestampedModel):
    """Child row attached to benchmark records."""

    __tablename__ = _TABLE_NOTES

    id: int = ColumnField(primary_key=True, autoincrement=True)
    record_id: int = ColumnField(foreign_key=f"{_TABLE_RECORDS}.id", index=True)
    title: str = ColumnField(length=120)


class BenchRecord(TimestampedModel):
    """Main entity used in benchmark scenarios."""

    __tablename__ = _TABLE_RECORDS

    id: int = ColumnField(primary_key=True, autoincrement=True)
    owner_id: int = ColumnField(foreign_key=f"{_TABLE_USERS}.id", index=True)
    request_id: str = ColumnField(length=64, index=True)
    full_name: str = ColumnField(length=120)
    email: str = ColumnField(length=255, index=True)

    owner: BenchUser = RelationField(
        foreign_key=f"{_TABLE_USERS}.id",
        cardinality=Cardinality.MANY_TO_ONE,
        profiles=("with_details",),
        depends_on=(f"{_TABLE_USERS}:id",),
    )
    notes: list[BenchNote] = RelationField(
        foreign_key="record_id",
        cardinality=Cardinality.ONE_TO_MANY,
        profiles=("with_details",),
        depends_on=(f"{_TABLE_NOTES}:record_id",),
    )
    has_notes: bool = ProjectionField(
        loader=ExistsLoader(model=BenchNote, via="notes"),
        profiles=("default", "with_details"),
        depends_on=(f"{_TABLE_NOTES}:record_id",),
        default=False,
    )
    notes_count: int = ProjectionField(
        loader=CountLoader(model=BenchNote, via="notes"),
        profiles=("with_details",),
        depends_on=(f"{_TABLE_NOTES}:record_id",),
        default=0,
    )
    note_snippets: list[dict[str, Any]] = ProjectionField(
        loader=JoinFieldsLoader(
            model=BenchNote,
            value_columns=("id", "title"),
            via="notes",
        ),
        profiles=("with_details",),
        depends_on=(f"{_TABLE_NOTES}:record_id",),
        default=[],
    )


class PingResponse(Response):
    """Response payload for ping endpoint."""

    status: str


class DatasetSummary(Response):
    """Dataset counts for benchmark visibility and reproducibility."""

    users: int
    records: int
    notes: int
    notes_per_record: int


class CreateBenchUser(Command, frozen=True):
    """Seed payload for benchmark users."""

    name: str
    email: str


class CreateBenchRecord(Command, frozen=True):
    """Seed payload for benchmark records."""

    owner_id: int
    request_id: str
    full_name: str
    email: str


class CreateBenchNote(Command, frozen=True):
    """Seed payload for benchmark notes."""

    record_id: int
    title: str


class UpdateBenchRecordEmail(Command, frozen=True):
    """Update payload for benchmark record email updates."""

    email: str


class PricingPreviewCommand(Command, frozen=True):
    """Input command for compute-heavy pricing update scenario."""

    email: str
    country: str
    unit_price: float
    quantity: int
    discount_pct: float = 0.0
    coupon_code: str | None = None
    vip: bool = False
    normalized_email: str = ""
    effective_discount_pct: float = 0.0
    subtotal: float = 0.0
    discount_amount: float = 0.0
    shipping_cost: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0


class PricingPreviewResponse(Response):
    """Output payload with deterministic computed amounts."""

    normalized_email: str
    country: str
    quantity: int
    unit_price: float
    subtotal: float
    effective_discount_pct: float
    discount_amount: float
    shipping_cost: float
    tax_rate: float
    tax_amount: float
    total: float


def _seed_notes_per_record() -> int:
    return int(os.getenv("BENCH_NOTES_PER_RECORD", "3"))


def _normalize_email(raw: str) -> str:
    return raw.strip().lower()


def _normalize_country(raw: str) -> str:
    return raw.strip().upper()


def _is_supported_country(country: str) -> bool:
    return country in _COUNTRY_TAX_RATES


def _is_supported_coupon(coupon_code: str | None) -> bool:
    return coupon_code is None or coupon_code in _COUPON_BONUS_DISCOUNT


def _effective_discount(discount_pct: float, coupon_code: str | None, vip: bool) -> float:
    coupon_extra = _COUPON_BONUS_DISCOUNT.get(coupon_code or "", 0.0)
    vip_extra = 2.0 if vip else 0.0
    return min(90.0, discount_pct + coupon_extra + vip_extra)


def _compute_subtotal(unit_price: float, quantity: int) -> float:
    return unit_price * quantity


def _compute_discount_amount(subtotal: float, effective_discount_pct: float) -> float:
    return subtotal * (effective_discount_pct / 100.0)


def _compute_shipping_cost(subtotal: float, discount_amount: float, coupon_code: str | None) -> float:
    taxable = max(0.0, subtotal - discount_amount)
    return 0.0 if taxable >= 100.0 or coupon_code == "SHIPFREE" else 7.5


def _compute_tax_rate(country: str) -> float:
    return _COUNTRY_TAX_RATES[country]


def _compute_tax_amount(subtotal: float, discount_amount: float, tax_rate: float) -> float:
    taxable = max(0.0, subtotal - discount_amount)
    return taxable * tax_rate


def _compute_total(subtotal: float, discount_amount: float, shipping_cost: float, tax_amount: float) -> float:
    taxable = max(0.0, subtotal - discount_amount)
    return taxable + shipping_cost + tax_amount


class PingUseCase(UseCase[BenchRecord, PingResponse]):
    """Lightweight endpoint used to verify server readiness."""

    async def execute(self) -> PingResponse:
        return PingResponse(status="ok")


class ListBenchRecordsUseCase(UseCase[BenchRecord, PageResult[BenchRecord] | CursorResult[BenchRecord]]):
    """List records through QuerySpec (offset and cursor)."""

    async def execute(
        self,
        query: QuerySpec,
        profile: str = "default",
    ) -> PageResult[BenchRecord] | CursorResult[BenchRecord]:
        return await self.main_repo.list_with_query(query, profile=profile)


class DatasetSummaryUseCase(UseCase[BenchRecord, DatasetSummary]):
    """Expose benchmark dataset counts with SQL COUNT(*) and on-demand seed."""

    def __init__(
        self,
        user_repo: RepoFor[BenchUser],
        record_repo: RepoFor[BenchRecord],
        note_repo: RepoFor[BenchNote],
    ) -> None:
        self._user_repo = user_repo
        self._record_repo = record_repo
        self._note_repo = note_repo

    async def execute(self) -> DatasetSummary:
        users, records, notes = await self._counts()
        if records == 0:
            await self._seed()
            users, records, notes = await self._counts()

        return DatasetSummary(
            users=users,
            records=records,
            notes=notes,
            notes_per_record=_seed_notes_per_record(),
        )

    async def _counts(self) -> tuple[int, int, int]:
        users, records, notes = await asyncio.gather(
            self._user_repo.count(),
            self._record_repo.count(),
            self._note_repo.count(),
        )
        return int(users), int(records), int(notes)

    async def _seed(self) -> None:
        users_total = max(1, int(os.getenv("BENCH_SEED_USERS", "120")))
        records_total = max(1, int(os.getenv("BENCH_SEED_RECORDS", "1200")))
        notes_per_record = max(0, _seed_notes_per_record())

        created_users: list[BenchUser] = []
        for i in range(1, users_total + 1):
            created = await self._user_repo.create(
                CreateBenchUser(name=f"bench-user-{i}", email=f"bench-user-{i}@example.com")
            )
            created_users.append(created)

        for i in range(1, records_total + 1):
            owner = created_users[(i - 1) % len(created_users)]
            created_record = await self._record_repo.create(
                CreateBenchRecord(
                    owner_id=owner.id,
                    request_id=f"req-{i}",
                    full_name=f"Record {i}",
                    email=f"record-{i}@example.com",
                )
            )
            for n in range(1, notes_per_record + 1):
                await self._note_repo.create(
                    CreateBenchNote(record_id=created_record.id, title=f"note-{created_record.id}-{n}")
                )


class PricingPreviewUseCase(UseCase[BenchRecord, PricingPreviewResponse]):
    """Custom update scenario using computes/rules before persistence."""

    computes = (
        Compute.set(F(PricingPreviewCommand).normalized_email).from_command(
            F(PricingPreviewCommand).email,
            via=_normalize_email,
        ),
        Compute.set(F(PricingPreviewCommand).country).from_command(
            F(PricingPreviewCommand).country,
            via=_normalize_country,
        ),
        Compute.set(F(PricingPreviewCommand).effective_discount_pct).from_command(
            F(PricingPreviewCommand).discount_pct,
            F(PricingPreviewCommand).coupon_code,
            F(PricingPreviewCommand).vip,
            via=_effective_discount,
        ),
        Compute.set(F(PricingPreviewCommand).subtotal).from_command(
            F(PricingPreviewCommand).unit_price,
            F(PricingPreviewCommand).quantity,
            via=_compute_subtotal,
        ),
        Compute.set(F(PricingPreviewCommand).discount_amount).from_command(
            F(PricingPreviewCommand).subtotal,
            F(PricingPreviewCommand).effective_discount_pct,
            via=_compute_discount_amount,
        ),
        Compute.set(F(PricingPreviewCommand).shipping_cost).from_command(
            F(PricingPreviewCommand).subtotal,
            F(PricingPreviewCommand).discount_amount,
            F(PricingPreviewCommand).coupon_code,
            via=_compute_shipping_cost,
        ),
        Compute.set(F(PricingPreviewCommand).tax_rate).from_command(
            F(PricingPreviewCommand).country,
            via=_compute_tax_rate,
        ),
        Compute.set(F(PricingPreviewCommand).tax_amount).from_command(
            F(PricingPreviewCommand).subtotal,
            F(PricingPreviewCommand).discount_amount,
            F(PricingPreviewCommand).tax_rate,
            via=_compute_tax_amount,
        ),
        Compute.set(F(PricingPreviewCommand).total).from_command(
            F(PricingPreviewCommand).subtotal,
            F(PricingPreviewCommand).discount_amount,
            F(PricingPreviewCommand).shipping_cost,
            F(PricingPreviewCommand).tax_amount,
            via=_compute_total,
        ),
    )

    rules = (
        Rule.check(
            F(PricingPreviewCommand).unit_price,
            via=lambda value: value <= 0,
            message="unit_price must be > 0",
        ),
        Rule.check(
            F(PricingPreviewCommand).quantity,
            via=lambda value: value <= 0 or value > 100,
            message="quantity must be between 1 and 100",
        ),
        Rule.check(
            F(PricingPreviewCommand).discount_pct,
            via=lambda value: value < 0 or value > 90,
            message="discount_pct must be between 0 and 90",
        ),
        Rule.check(
            F(PricingPreviewCommand).country,
            via=lambda value: not _is_supported_country(value),
            message="Unsupported country",
        ),
        Rule.check(
            F(PricingPreviewCommand).coupon_code,
            via=lambda value: not _is_supported_coupon(value),
            message="Unsupported coupon",
        ),
    )

    async def execute(
        self,
        record_id: int,
        cmd: PricingPreviewCommand = Input(),
    ) -> PricingPreviewResponse:
        updated = await self.main_repo.update(record_id, UpdateBenchRecordEmail(email=cmd.normalized_email))
        if updated is None:
            raise NotFound("BenchRecord", id=record_id)

        return PricingPreviewResponse(
            normalized_email=cmd.normalized_email,
            country=cmd.country,
            quantity=cmd.quantity,
            unit_price=cmd.unit_price,
            subtotal=round(cmd.subtotal, 2),
            effective_discount_pct=round(cmd.effective_discount_pct, 2),
            discount_amount=round(cmd.discount_amount, 2),
            shipping_cost=round(cmd.shipping_cost, 2),
            tax_rate=round(cmd.tax_rate, 4),
            tax_amount=round(cmd.tax_amount, 2),
            total=round(cmd.total, 2),
        )


class BenchRecordsAutoInterface(RestInterface[BenchRecord]):
    """Auto CRUD endpoints for benchmark records."""

    prefix = "/bench/records"
    tags = ("Benchmark",)
    auto = True
    include = ("get", "update")
    profile_default = "default"
    allowed_profiles = ("default", "with_details")
    expose_profile = True
    pagination_mode = PaginationMode.CURSOR
    routes: tuple[RestRoute, ...] = ()


class BenchRecordsCustomInterface(RestInterface[BenchRecord]):
    """Custom benchmark endpoints not covered by autocrud."""

    prefix = "/bench/records"
    tags = ("Benchmark",)
    profile_default = "default"
    allowed_profiles = ("default", "with_details")
    expose_profile = True
    pagination_mode = PaginationMode.CURSOR
    routes = (
        RestRoute(
            use_case=ListBenchRecordsUseCase,
            method="GET",
            path="",
            expose_profile=True,
            summary="List records",
        ),
        RestRoute(
            use_case=PricingPreviewUseCase,
            method="POST",
            path="/{record_id}/pricing-preview",
            summary="Update with computes and rules",
        ),
    )


class BenchOpsInterface(RestInterface[BenchRecord]):
    """Operational benchmark endpoints."""

    prefix = "/bench"
    tags = ("Benchmark",)
    routes = (
        RestRoute(use_case=PingUseCase, method="GET", path="/ping", summary="Ping"),
        RestRoute(use_case=DatasetSummaryUseCase, method="GET", path="/dataset", summary="Dataset summary"),
    )
