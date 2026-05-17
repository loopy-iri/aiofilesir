"""Common base for resource façades."""
from __future__ import annotations

from ..transport import Transport


class BaseResource:
    """Holds a reference to the shared :class:`Transport`."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
