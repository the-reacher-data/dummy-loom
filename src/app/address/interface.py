"""Address REST interface."""

from __future__ import annotations

from loom.rest.model import RestInterface, RestRoute

from app.address.model import Address
from app.address.use_cases import (
    CreateAddressUseCase,
    DeleteAddressUseCase,
    GetAddressUseCase,
    ListAddressesUseCase,
    UpdateAddressUseCase,
)


class AddressRestInterface(RestInterface[Address]):
    """REST interface for user addresses."""

    prefix = "/users"
    tags = ("UserAddresses",)
    routes = (
        RestRoute(
            use_case=CreateAddressUseCase,
            method="POST",
            path="/{user_id}/addresses/",
            status_code=201,
            summary="Create user address",
            description="Create an address for the selected user.",
        ),
        RestRoute(
            use_case=ListAddressesUseCase,
            method="GET",
            path="/{user_id}/addresses/",
            summary="List user addresses",
            description="List addresses owned by the selected user.",
        ),
        RestRoute(
            use_case=GetAddressUseCase,
            method="GET",
            path="/{user_id}/addresses/{address_id}",
            summary="Get user address",
            description="Get one address for the selected user.",
        ),
        RestRoute(
            use_case=UpdateAddressUseCase,
            method="PATCH",
            path="/{user_id}/addresses/{address_id}",
            summary="Update user address",
            description="Partially update one address owned by the selected user.",
        ),
        RestRoute(
            use_case=DeleteAddressUseCase,
            method="DELETE",
            path="/{user_id}/addresses/{address_id}",
            summary="Delete user address",
            description="Delete one address owned by the selected user.",
        ),
    )
