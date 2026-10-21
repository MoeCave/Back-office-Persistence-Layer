"""Router: maps a validated request to a service call.

The router is stateless.  It looks the handler up in the routing table
(``src.server.routes``), runs it against the right service and converts
the result, or any exception, into a protocol-ready response envelope.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.common import protocol
from src.server.errors import AppError, UnknownActionError
from src.server.routes import ROUTES
from src.server.services import (
    CategoryService,
    FighterService,
    MatchService,
    RegistrationService,
    TournamentService,
)

log = logging.getLogger(__name__)

# resource name -> attribute that holds its service instance
_SERVICE_ATTRIBUTES = {
    "fighters": "_fighters",
    "tournaments": "_tournaments",
    "categories": "_categories",
    "matches": "_matches",
    "registrations": "_registrations",
}


class Router:
    """Receives request dicts, dispatches to services, returns responses."""

    def __init__(self, session_factory) -> None:
        self._fighters = FighterService(session_factory)
        self._tournaments = TournamentService(session_factory)
        self._categories = CategoryService(session_factory)
        self._matches = MatchService(session_factory)
        self._registrations = RegistrationService(session_factory)

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dispatch *request* and return a response envelope."""
        resource = request.get("resource", "")
        action = request.get("action", "")
        payload = request.get("payload") or {}
        try:
            return protocol.ok(self._dispatch(resource, action, payload))
        except Exception as exc:  # noqa: BLE001 - mapped to a response
            return self._to_error_response(exc)

    def _dispatch(
        self, resource: str, action: str, payload: dict[str, Any]
    ) -> Any:
        actions = ROUTES.get(resource)
        if actions is None:
            raise UnknownActionError(f"Unknown resource: '{resource}'.")
        handler = actions.get(action)
        if handler is None:
            raise UnknownActionError(
                f"Unknown action '{action}' for resource '{resource}'."
            )
        service = getattr(self, _SERVICE_ATTRIBUTES[resource])
        return handler(service, payload)

    @staticmethod
    def _to_error_response(exc: Exception) -> dict[str, Any]:
        """Translate an exception into an error envelope."""
        if isinstance(exc, AppError):
            return protocol.error(str(exc), exc.code)
        if isinstance(exc, ValueError):
            return protocol.error(str(exc), protocol.ErrorCode.BAD_REQUEST)
        if isinstance(exc, IntegrityError):
            log.warning("Integrity error: %s", exc)
            return protocol.error(
                "The operation violates a data constraint "
                "(unknown referenced id or duplicate value).",
                protocol.ErrorCode.CONFLICT,
            )
        log.exception("Unexpected error while handling a request")
        return protocol.error(
            "Internal server error.", protocol.ErrorCode.INTERNAL_ERROR
        )
