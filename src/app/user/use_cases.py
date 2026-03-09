"""User use cases with business rules."""

from __future__ import annotations

import re

from loom.core.command import Command, Patch
from loom.core.errors import NotFound
from loom.core.repository.abc.query import CursorResult, PageResult, QuerySpec
from loom.core.use_case import F, Exists, Input, LoadById, Rule
from loom.core.use_case.use_case import UseCase

from app.user.model import User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CreateUser(Command, frozen=True):
    full_name: str
    email: str


class UpdateUser(Command, frozen=True):
    full_name: Patch[str] = None
    email: Patch[str] = None


def _name_must_not_be_blank(full_name: str) -> str | None:
    if not full_name.strip():
        return "full_name must not be blank"
    return None


def _email_must_be_valid(email: str) -> str | None:
    if not _EMAIL_RE.fullmatch(email):
        return "email must be valid"
    return None


def _email_already_exists(_: Command, __: frozenset[str], email_exists: bool) -> bool:
    return email_exists


def _email_update_is_conflicting(
    cmd: Command,
    __: frozenset[str],
    current_user: User,
    email_exists: bool,
) -> bool:
    update_cmd = cmd if isinstance(cmd, UpdateUser) else None
    if update_cmd is None:
        return False
    next_email = update_cmd.email
    if next_email is None:
        return False
    if next_email == current_user.email:
        return False
    return email_exists


CREATE_NAME_RULE = Rule.check(F(CreateUser).full_name, via=_name_must_not_be_blank)
CREATE_EMAIL_FORMAT_RULE = Rule.check(F(CreateUser).email, via=_email_must_be_valid)
CREATE_EMAIL_UNIQUE_RULE = Rule.forbid(
    _email_already_exists,
    message="email already exists",
).from_params("email_exists")

UPDATE_NAME_RULE = Rule.check(F(UpdateUser).full_name, via=_name_must_not_be_blank).when_present(
    F(UpdateUser).full_name
)
UPDATE_EMAIL_FORMAT_RULE = Rule.check(F(UpdateUser).email, via=_email_must_be_valid).when_present(
    F(UpdateUser).email
)
UPDATE_EMAIL_UNIQUE_RULE = (
    Rule.forbid(
        _email_update_is_conflicting,
        message="email already exists",
    )
    .from_params("current_user", "email_exists")
    .when_present(F(UpdateUser).email)
)


class CreateUserUseCase(UseCase[User, User]):
    rules = [
        CREATE_NAME_RULE,
        CREATE_EMAIL_FORMAT_RULE,
        CREATE_EMAIL_UNIQUE_RULE,
    ]

    async def execute(
        self,
        cmd: CreateUser = Input(),
        email_exists: bool = Exists(User, from_command="email", against="email"),
    ) -> User:
        return await self.main_repo.create(cmd)


class GetUserUseCase(UseCase[User, User]):
    async def execute(self, user_id: int, profile: str = "default") -> User:
        user = await self.main_repo.get_by_id(user_id, profile=profile)
        if user is None:
            raise NotFound("User", id=user_id)
        return user


class ListUsersUseCase(UseCase[User, PageResult[User] | CursorResult[User]]):
    async def execute(
        self,
        query: QuerySpec,
        profile: str = "default",
    ) -> PageResult[User] | CursorResult[User]:
        return await self.main_repo.list_with_query(query, profile=profile)


class UpdateUserUseCase(UseCase[User, User | None]):
    rules = [
        UPDATE_NAME_RULE,
        UPDATE_EMAIL_FORMAT_RULE,
        UPDATE_EMAIL_UNIQUE_RULE,
    ]

    async def execute(
        self,
        user_id: int,
        cmd: UpdateUser = Input(),
        current_user: User = LoadById(User, by="user_id"),
        email_exists: bool = Exists(User, from_command="email", against="email"),
    ) -> User | None:
        return await self.main_repo.update(user_id, cmd)


class DeleteUserUseCase(UseCase[User, bool]):
    async def execute(self, user_id: int) -> bool:
        return await self.main_repo.delete(user_id)
