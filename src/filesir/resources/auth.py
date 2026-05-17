"""``/auth/*`` endpoints."""
from __future__ import annotations

from ..models import User
from .base import BaseResource


class AuthResource(BaseResource):
    """Wraps ``/auth/register`` and ``/auth/login``.

    Both endpoints are called *without* the Authorization header so this resource
    works equally well before any token is set on the client.
    """

    async def register(
        self,
        *,
        email: str,
        password: str,
        token_name: str | None = None,
    ) -> User:
        body = {"email": email, "password": password}
        if token_name is not None:
            body["token_name"] = token_name
        data = await self._transport.request_json(
            "POST",
            "/auth/register",
            json=body,
            authenticated=False,
        )
        return _user_from_envelope(data)

    async def login(
        self,
        *,
        email: str,
        password: str,
        token_name: str | None = None,
    ) -> User:
        body = {"email": email, "password": password}
        if token_name is not None:
            body["token_name"] = token_name
        data = await self._transport.request_json(
            "POST",
            "/auth/login",
            json=body,
            authenticated=False,
        )
        return _user_from_envelope(data)


def _user_from_envelope(data: object) -> User:
    if isinstance(data, dict) and "user" in data:
        return User.model_validate(data["user"])
    return User.model_validate(data)
