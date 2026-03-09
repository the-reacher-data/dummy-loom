"""User REST interface."""

from __future__ import annotations

from loom.rest.model import RestInterface, RestRoute

from app.user.model import User
from app.user.use_cases import (
    CreateUserUseCase,
    DeleteUserUseCase,
    GetUserUseCase,
    ListUsersUseCase,
    UpdateUserUseCase,
)


class UserRestInterface(RestInterface[User]):
    """REST interface for users."""

    prefix = "/users"
    tags = ("Users",)
    routes = (
        RestRoute(
            use_case=CreateUserUseCase,
            method="POST",
            path="/",
            status_code=201,
            summary="Create user",
            description="Create a new store user.",
        ),
        RestRoute(
            use_case=ListUsersUseCase,
            method="GET",
            path="/",
            summary="List users",
            description="List users with filtering, sorting, and pagination.",
        ),
        RestRoute(
            use_case=GetUserUseCase,
            method="GET",
            path="/{user_id}",
            summary="Get user",
            description="Get a user by id.",
        ),
        RestRoute(
            use_case=UpdateUserUseCase,
            method="PATCH",
            path="/{user_id}",
            summary="Update user",
            description="Partially update a user.",
        ),
        RestRoute(
            use_case=DeleteUserUseCase,
            method="DELETE",
            path="/{user_id}",
            summary="Delete user",
            description="Delete a user by id.",
        ),
    )
