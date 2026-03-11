"""Native FastAPI benchmark app with equivalent cursor/offset/detail contracts."""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, exists, func, select, text, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DEFAULT_DB_URL = "postgresql+asyncpg://store:store@127.0.0.1:5432/store"
DB_URL = os.getenv("BENCH_NATIVE_DATABASE_URL", DEFAULT_DB_URL)
SEED_USERS = int(os.getenv("BENCH_SEED_USERS", "120"))
SEED_RECORDS = int(os.getenv("BENCH_SEED_RECORDS", "1200"))
NOTES_PER_RECORD = int(os.getenv("BENCH_NOTES_PER_RECORD", "3"))
BENCH_RESET_ON_START = os.getenv("BENCH_RESET_ON_START", "1") not in {"0", "false", "False"}
BOOTSTRAP_LOCK_PATH = os.getenv("BENCH_BOOTSTRAP_LOCK_PATH", "/tmp/bench_fastapi_native_bootstrap.lock")
BOOTSTRAP_DONE_PATH = os.getenv("BENCH_BOOTSTRAP_DONE_PATH", "/tmp/bench_fastapi_native_bootstrap.done")
BOOTSTRAP_WAIT_SECONDS = float(os.getenv("BENCH_BOOTSTRAP_WAIT_SECONDS", "120"))


class Base(DeclarativeBase):
    """Base class for benchmark ORM models."""


class BenchUserSA(Base):
    """Owner entity used for details profile."""

    __tablename__ = "bench_users_native"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)


class BenchRecordSA(Base):
    """Main record entity used in benchmark scenarios."""

    __tablename__ = "bench_records_native"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("bench_users_native.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), index=True)


class BenchNoteSA(Base):
    """Child row used for details profile projections."""

    __tablename__ = "bench_notes_native"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    record_id: Mapped[int] = mapped_column(ForeignKey("bench_records_native.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))


class UpdateRecordRequest(BaseModel):
    """Body payload for plain record update scenario."""

    email: str


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


class PingResponse(BaseModel):
    """Health payload used by the benchmark runner."""

    status: str


class RecordBaseResponse(BaseModel):
    """Base output payload for record endpoints."""

    id: int
    owner_id: int
    request_id: str
    full_name: str
    email: str
    has_notes: bool


class RecordOwnerResponse(BaseModel):
    """Nested owner payload for details profile."""

    id: int
    name: str
    email: str


class RecordNoteResponse(BaseModel):
    """Nested note payload for details profile."""

    id: int
    record_id: int
    title: str


class RecordWithDetailsResponse(RecordBaseResponse):
    """Detailed output payload with relations and projections."""

    owner: RecordOwnerResponse
    notes: list[RecordNoteResponse]
    notes_count: int
    note_snippets: list[dict[str, Any]]


class CursorListResponse(BaseModel):
    """Cursor pagination response."""

    items: list[RecordBaseResponse]
    next_cursor: str | None
    has_next: bool


class OffsetListResponse(BaseModel):
    """Offset pagination response with total count."""

    items: list[RecordBaseResponse]
    total: int
    page: int
    limit: int
    pages: int
    has_next: bool


class DatasetSummaryResponse(BaseModel):
    """Dataset summary returned for benchmark reports."""

    users: int
    records: int
    notes: int
    notes_per_record: int


class PricingPreviewRequest(BaseModel):
    """Input payload for compute-heavy pricing preview benchmark."""

    email: str
    country: str
    unit_price: float
    quantity: int
    discount_pct: float = 0.0
    coupon_code: str | None = None
    vip: bool = False

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("country", mode="before")
    @classmethod
    def _normalize_country(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _validate_ranges(self) -> "PricingPreviewRequest":
        if self.country not in _COUNTRY_TAX_RATES:
            raise ValueError("Unsupported country")
        if self.unit_price <= 0:
            raise ValueError("unit_price must be > 0")
        if self.quantity <= 0 or self.quantity > 100:
            raise ValueError("quantity must be between 1 and 100")
        if self.discount_pct < 0 or self.discount_pct > 90:
            raise ValueError("discount_pct must be between 0 and 90")
        if self.coupon_code is not None and self.coupon_code not in _COUPON_BONUS_DISCOUNT:
            raise ValueError("Unsupported coupon")
        return self


class PricingPreviewResponse(BaseModel):
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


# pool_pre_ping=False matches Loom benchmark config (base.yaml).
# Both apps use SQLAlchemy defaults: pool_size=5, max_overflow=10.
engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=False)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Provide async SQLAlchemy session via FastAPI dependency."""

    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _seed_dataset() -> None:
    async with SessionLocal() as session:
        users = [
            BenchUserSA(name=f"bench-user-{i}", email=f"bench-user-{i}@example.com")
            for i in range(1, SEED_USERS + 1)
        ]
        session.add_all(users)
        await session.flush()

        records = []
        for i in range(1, SEED_RECORDS + 1):
            owner = users[(i - 1) % len(users)]
            records.append(
                BenchRecordSA(
                    owner_id=owner.id,
                    request_id=f"req-{i}",
                    full_name=f"Record {i}",
                    email=f"record-{i}@example.com",
                )
            )
        session.add_all(records)
        await session.flush()

        notes = []
        for record in records:
            for n in range(1, NOTES_PER_RECORD + 1):
                notes.append(BenchNoteSA(record_id=record.id, title=f"note-{record.id}-{n}"))
        session.add_all(notes)

        await session.commit()


async def _load_has_notes_ids(session: AsyncSession, record_ids: list[int]) -> set[int]:
    """Return record ids that have at least one related note."""

    if not record_ids:
        return set()
    ids = (
        await session.execute(
            select(BenchNoteSA.record_id).where(BenchNoteSA.record_id.in_(record_ids)).distinct()
        )
    ).scalars().all()
    return {int(record_id) for record_id in ids}


async def _reset_and_seed_dataset() -> None:
    """Reset benchmark schema and seed deterministic dataset."""

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await _seed_dataset()


async def _wait_for_bootstrap_done(timeout_seconds: float) -> None:
    """Wait until the bootstrap owner completes database setup."""

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if (not os.path.exists(BOOTSTRAP_LOCK_PATH)) and os.path.exists(BOOTSTRAP_DONE_PATH):
            return
        await asyncio.sleep(0.2)
    raise RuntimeError(
        "Timed out waiting for FastAPI benchmark bootstrap to finish"
    )


async def _bootstrap_once_for_workers() -> None:
    """Ensure schema reset/seed runs only once across multi-worker startup."""

    if not BENCH_RESET_ON_START:
        return

    lock_fd: int | None = None
    is_bootstrap_owner = False

    try:
        lock_fd = os.open(BOOTSTRAP_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        is_bootstrap_owner = True
    except FileExistsError:
        is_bootstrap_owner = False

    if is_bootstrap_owner:
        try:
            if os.path.exists(BOOTSTRAP_DONE_PATH):
                os.remove(BOOTSTRAP_DONE_PATH)
            await _reset_and_seed_dataset()
            with open(BOOTSTRAP_DONE_PATH, "w", encoding="utf-8") as marker:
                marker.write("ok\n")
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            if os.path.exists(BOOTSTRAP_LOCK_PATH):
                os.remove(BOOTSTRAP_LOCK_PATH)
        return

    await _wait_for_bootstrap_done(BOOTSTRAP_WAIT_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize benchmark dataset safely for multi-worker startup."""

    await _bootstrap_once_for_workers()
    try:
        yield
    finally:
        await engine.dispose()


def _base_record_response(row: BenchRecordSA, *, has_notes: bool) -> RecordBaseResponse:
    return RecordBaseResponse(
        id=row.id,
        owner_id=row.owner_id,
        request_id=row.request_id,
        full_name=row.full_name,
        email=row.email,
        has_notes=has_notes,
    )


def create_app() -> FastAPI:
    """Build native FastAPI benchmark app."""

    app = FastAPI(title="fastapi-native-benchmark", lifespan=lifespan)

    @app.get("/bench/ping", response_model=PingResponse)
    async def ping() -> PingResponse:
        return PingResponse(status="ok")

    @app.get("/bench/dataset", response_model=DatasetSummaryResponse)
    async def dataset(session: AsyncSession = Depends(get_session)) -> DatasetSummaryResponse:
        user_count = int((await session.execute(select(func.count()).select_from(BenchUserSA))).scalar() or 0)
        record_count = int(
            (await session.execute(select(func.count()).select_from(BenchRecordSA))).scalar() or 0
        )
        note_count = int((await session.execute(select(func.count()).select_from(BenchNoteSA))).scalar() or 0)
        return DatasetSummaryResponse(
            users=user_count,
            records=record_count,
            notes=note_count,
            notes_per_record=NOTES_PER_RECORD,
        )

    @app.patch("/bench/records/{record_id}", response_model=RecordBaseResponse)
    async def update_record(
        record_id: int,
        payload: UpdateRecordRequest,
        session: AsyncSession = Depends(get_session),
    ) -> RecordBaseResponse:
        # Single UPDATE … RETURNING round-trip (mirrors Loom's repo.update() + RETURNING).
        stmt = (
            sa_update(BenchRecordSA)
            .where(BenchRecordSA.id == record_id)
            .values(email=payload.email)
            .returning(BenchRecordSA)
            .execution_options(synchronize_session=False)
        )
        row = (await session.execute(stmt)).scalars().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Record not found")

        # EXISTS mirrors Loom's ExistsLoader SQL path on the "default" profile.
        has_notes_val = bool(
            (
                await session.execute(
                    select(exists().where(BenchNoteSA.record_id == row.id))
                )
            ).scalar()
        )
        return _base_record_response(row, has_notes=has_notes_val)


    @app.post("/bench/records/{record_id}/pricing-preview", response_model=PricingPreviewResponse)
    async def pricing_preview(
        record_id: int,
        payload: PricingPreviewRequest,
        session: AsyncSession = Depends(get_session),
    ) -> PricingPreviewResponse:
        coupon_extra = _COUPON_BONUS_DISCOUNT.get(payload.coupon_code or "", 0.0)
        vip_extra = 2.0 if payload.vip else 0.0
        effective_discount_pct = min(90.0, payload.discount_pct + coupon_extra + vip_extra)

        subtotal = payload.unit_price * payload.quantity
        discount_amount = subtotal * (effective_discount_pct / 100.0)
        taxable = max(0.0, subtotal - discount_amount)
        shipping_cost = 0.0 if taxable >= 100.0 or payload.coupon_code == "SHIPFREE" else 7.5
        tax_rate = _COUNTRY_TAX_RATES[payload.country]
        tax_amount = taxable * tax_rate
        total = taxable + shipping_cost + tax_amount

        row = await session.get(BenchRecordSA, record_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Record not found")
        row.email = payload.email
        await session.flush()

        return PricingPreviewResponse(
            normalized_email=payload.email,
            country=payload.country,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            subtotal=round(subtotal, 2),
            effective_discount_pct=round(effective_discount_pct, 2),
            discount_amount=round(discount_amount, 2),
            shipping_cost=round(shipping_cost, 2),
            tax_rate=round(tax_rate, 4),
            tax_amount=round(tax_amount, 2),
            total=round(total, 2),
        )

    @app.get("/bench/records/{record_id}", response_model=RecordBaseResponse | RecordWithDetailsResponse)
    async def get_record(
        record_id: int,
        profile: str = Query(default="default"),
        session: AsyncSession = Depends(get_session),
    ) -> RecordBaseResponse | RecordWithDetailsResponse:
        row = await session.get(BenchRecordSA, record_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Record not found")

        if profile != "with_details":
            # "default" profile: notes relation not loaded → SQL EXISTS (mirrors Loom ExistsLoader SQL path).
            has_notes_val = bool(
                (
                    await session.execute(
                        select(exists().where(BenchNoteSA.record_id == row.id))
                    )
                ).scalar()
            )
            return _base_record_response(row, has_notes=has_notes_val)

        # "with_details": load owner and notes (3 queries total, same as Loom).
        owner = await session.get(BenchUserSA, row.owner_id)
        if owner is None:
            raise HTTPException(status_code=500, detail="Owner not found")

        notes_rows = (
            await session.execute(
                select(BenchNoteSA)
                .where(BenchNoteSA.record_id == row.id)
                .order_by(BenchNoteSA.id.asc())
            )
        ).scalars().all()

        # Derive has_notes from the already-loaded notes list — no extra query.
        # Mirrors Loom's memory-path ExistsLoader/_MemoryExistsLoader behaviour.
        has_notes_val = len(notes_rows) > 0
        notes = [RecordNoteResponse(id=n.id, record_id=n.record_id, title=n.title) for n in notes_rows]
        snippets = [{"id": n.id, "title": n.title} for n in notes_rows]

        return RecordWithDetailsResponse(
            **_base_record_response(row, has_notes=has_notes_val).model_dump(),
            owner=RecordOwnerResponse(id=owner.id, name=owner.name, email=owner.email),
            notes=notes,
            notes_count=len(notes),
            note_snippets=snippets,
        )

    @app.get("/bench/records", response_model=CursorListResponse | OffsetListResponse)
    async def list_records(
        pagination: str = Query(default="cursor"),
        after: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=25, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
    ) -> CursorListResponse | OffsetListResponse:
        stmt = select(BenchRecordSA).order_by(BenchRecordSA.id.asc())

        if pagination == "offset":
            offset = (page - 1) * limit
            items = (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()
            notes_ids = await _load_has_notes_ids(session, [row.id for row in items])
            total = int((await session.execute(select(func.count()).select_from(BenchRecordSA))).scalar() or 0)
            pages = max(1, math.ceil(total / limit))
            return OffsetListResponse(
                items=[_base_record_response(row, has_notes=row.id in notes_ids) for row in items],
                total=total,
                page=page,
                limit=limit,
                pages=pages,
                has_next=(offset + len(items)) < total,
            )

        if after is not None:
            try:
                cursor_id = int(after)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid cursor") from exc
            stmt = stmt.where(BenchRecordSA.id > cursor_id)

        rows = (await session.execute(stmt.limit(limit + 1))).scalars().all()
        has_next = len(rows) > limit
        page_rows = rows[:limit]
        notes_ids = await _load_has_notes_ids(session, [row.id for row in page_rows])
        next_cursor = str(page_rows[-1].id) if has_next and page_rows else None
        return CursorListResponse(
            items=[_base_record_response(row, has_notes=row.id in notes_ids) for row in page_rows],
            next_cursor=next_cursor,
            has_next=has_next,
        )

    return app


app = create_app()
