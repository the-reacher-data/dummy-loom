"""Address use cases scoped under user."""

from __future__ import annotations

from loom.core.command import Command, Patch
from loom.core.errors import NotFound
from loom.core.repository.abc.query import CursorResult, FilterGroup, FilterOp, FilterSpec, PageResult, QuerySpec
from loom.core.use_case import Exists, Input, OnMissing
from loom.core.use_case.use_case import UseCase

from app.address.model import Address
from app.user.model import User


class CreateUserAddress(Command, frozen=True):
    label: str
    street: str
    city: str
    country: str
    zip_code: str


class CreateAddressRecord(Command, frozen=True):
    user_id: int
    label: str
    street: str
    city: str
    country: str
    zip_code: str


class UpdateAddress(Command, frozen=True):
    label: Patch[str] = None
    street: Patch[str] = None
    city: Patch[str] = None
    country: Patch[str] = None
    zip_code: Patch[str] = None


def _ensure_owned_by_user(address: Address | None, *, user_id: int, address_id: int) -> Address:
    if address is None or address.user_id != user_id:
        raise NotFound("Address", id=address_id)
    return address


class CreateAddressUseCase(UseCase[Address, Address]):
    async def execute(
        self,
        user_id: int,
        cmd: CreateUserAddress = Input(),
        _user_exists: bool = Exists(User, from_param="user_id", against="id", on_missing=OnMissing.RAISE),
    ) -> Address:
        payload = CreateAddressRecord(
            user_id=user_id,
            label=cmd.label,
            street=cmd.street,
            city=cmd.city,
            country=cmd.country,
            zip_code=cmd.zip_code,
        )
        return await self.main_repo.create(payload)


class GetAddressUseCase(UseCase[Address, Address]):
    async def execute(self, user_id: int, address_id: int, profile: str = "default") -> Address:
        address = await self.main_repo.get_by_id(address_id, profile=profile)
        return _ensure_owned_by_user(address, user_id=user_id, address_id=address_id)


class ListAddressesUseCase(UseCase[Address, PageResult[Address] | CursorResult[Address]]):
    async def execute(
        self,
        user_id: int,
        query: QuerySpec,
        profile: str = "default",
    ) -> PageResult[Address] | CursorResult[Address]:
        scoped_query = QuerySpec(
            filters=FilterGroup(
                filters=(FilterSpec(field="user_id", op=FilterOp.EQ, value=user_id),),
            ),
            sort=query.sort,
            pagination=query.pagination,
            limit=query.limit,
            page=query.page,
            cursor=query.cursor,
        )
        return await self.main_repo.list_with_query(scoped_query, profile=profile)


class UpdateAddressUseCase(UseCase[Address, Address]):
    async def execute(self, user_id: int, address_id: int, cmd: UpdateAddress = Input()) -> Address:
        current = await self.main_repo.get_by_id(address_id)
        _ensure_owned_by_user(current, user_id=user_id, address_id=address_id)

        updated = await self.main_repo.update(address_id, cmd)
        if updated is None:
            raise NotFound("Address", id=address_id)
        return updated


class DeleteAddressUseCase(UseCase[Address, bool]):
    async def execute(self, user_id: int, address_id: int) -> bool:
        current = await self.main_repo.get_by_id(address_id)
        _ensure_owned_by_user(current, user_id=user_id, address_id=address_id)
        return await self.main_repo.delete(address_id)
