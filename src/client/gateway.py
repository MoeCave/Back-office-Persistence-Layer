"""
client/gateway.py — TCP gateway used by all client-side menus.

The ServerGateway replaces direct UnitOfWork calls on the client side.
It wraps the protocol framing and exposes typed methods that mirror the
server-side service interface.

All methods raise ServerError on protocol-level failures and ValueError
when the server reports a domain error (success=false).
"""

from __future__ import annotations

import socket
from typing import Any

from src.common.protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ErrorCode,
    receive_message,
    send_message,
)


class ServerError(Exception):
    """Raised when the server responds with success=false.

    ``code`` holds the machine-readable ``error_code`` of the response.
    """

    def __init__(
        self, message: str, code: str = ErrorCode.BAD_REQUEST
    ) -> None:
        super().__init__(message)
        self.code = code


class ConnectionFailedError(Exception):
    """Raised when the TCP connection to the server cannot be established."""


class ServerGateway:
    """Persistent TCP connection to the server.

    Usage:
        gw = ServerGateway()
        gw.connect()
        fighters = gw.fighters.list_all()
        gw.close()

    Or as a context manager:
        with ServerGateway() as gw:
            fighters = gw.fighters.list_all()
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None

        # Sub-namespaces (populated after connect)
        self.fighters: _FighterProxy
        self.tournaments: _TournamentProxy
        self.categories: _CategoryProxy
        self.matches: _MatchProxy
        self.registrations: _RegistrationProxy

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Open a blocking TCP connection to the server."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self._host, self._port))
            self._sock = sock
        except OSError as exc:
            raise ConnectionFailedError(
                f"Cannot connect to server at {self._host}:{self._port}. "
                f"Is the server running? ({exc})"
            ) from exc

        self.fighters = _FighterProxy(self)
        self.tournaments = _TournamentProxy(self)
        self.categories = _CategoryProxy(self)
        self.matches = _MatchProxy(self)
        self.registrations = _RegistrationProxy(self)

    def close(self) -> None:
        """Close the TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> "ServerGateway":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Raw request ──────────────────────────────────────────────────────────

    def request(
        self,
        resource: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Send one request and return the data field on success.

        Raises:
            ServerError:          server returned success=false.
            ConnectionFailedError: socket is not open.
            ConnectionError:      connection dropped mid-request.
        """
        if self._sock is None:
            raise ConnectionFailedError("Not connected. Call connect() first.")

        envelope = {
            "resource": resource,
            "action": action,
            "payload": payload or {},
        }
        send_message(self._sock, envelope)
        response = receive_message(self._sock)

        if not response.get("success"):
            raise ServerError(
                response.get("error") or "Unknown server error.",
                response.get("error_code") or ErrorCode.BAD_REQUEST,
            )
        return response.get("data")

    def get_or_none(
        self,
        resource: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Like :meth:`request`, but return None when nothing is found.

        Only ``NOT_FOUND`` is swallowed; any other server error is raised.
        """
        try:
            return self.request(resource, action, payload)
        except ServerError as exc:
            if exc.code == ErrorCode.NOT_FOUND:
                return None
            raise


# ── Resource proxies (one per domain entity) ─────────────────────────────────


class _FighterProxy:
    def __init__(self, gw: ServerGateway) -> None:
        self._gw = gw

    def list_all(self) -> list[dict[str, Any]]:
        return self._gw.request("fighters", "list")

    def list_paginated(
        self, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        return self._gw.request(
            "fighters",
            "list_paginated",
            {"page": page, "page_size": page_size},
        )

    def get(self, fighter_id: int) -> dict[str, Any] | None:
        return self._gw.get_or_none(
            "fighters", "get", {"fighter_id": fighter_id}
        )

    def create(self, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request("fighters", "create", kwargs)

    def update(self, fighter_id: int, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request(
            "fighters", "update", {"fighter_id": fighter_id, **kwargs}
        )

    def delete(self, fighter_id: int) -> None:
        self._gw.request("fighters", "delete", {"fighter_id": fighter_id})

    def count(self) -> int:
        result = self.list_paginated(page=1, page_size=1)
        return result.get("total", 0)

    def get_paginated(self, page: int = 1, page_size: int = 10) -> list[dict]:
        result = self.list_paginated(page=page, page_size=page_size)
        return result.get("items", [])

    def get_by_last_name(self, last_name: str) -> list[dict[str, Any]]:
        return self._gw.request(
            "fighters", "search_by_last_name", {"last_name": last_name}
        )

    def get_by_belt_level(self, belt_level: str) -> list[dict[str, Any]]:
        return self._gw.request(
            "fighters", "search_by_belt_level", {"belt_level": belt_level}
        )

    def get_by_country(self, country: str) -> list[dict[str, Any]]:
        return self._gw.request(
            "fighters", "search_by_country", {"country": country}
        )

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        return self._gw.request(
            "fighters", "search_by_email", {"email": email}
        )

    def upsert_medical_record(
        self, fighter_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        return self._gw.request(
            "fighters",
            "upsert_medical_record",
            {"fighter_id": fighter_id, **kwargs},
        )

    def approve_registration(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> dict[str, Any]:
        return self._gw.request(
            "fighters",
            "approve_registration",
            {
                "fighter_id": fighter_id,
                "category_id": category_id,
                "tournament_id": tournament_id,
            },
        )


class _TournamentProxy:
    def __init__(self, gw: ServerGateway) -> None:
        self._gw = gw

    def list_all(self) -> list[dict[str, Any]]:
        return self._gw.request("tournaments", "list")

    def get(self, tournament_id: int) -> dict[str, Any] | None:
        return self._gw.get_or_none(
            "tournaments", "get", {"tournament_id": tournament_id}
        )

    def create(self, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request("tournaments", "create", kwargs)

    def update(self, tournament_id: int, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request(
            "tournaments",
            "update",
            {"tournament_id": tournament_id, **kwargs},
        )

    def delete(self, tournament_id: int) -> None:
        self._gw.request(
            "tournaments", "delete", {"tournament_id": tournament_id}
        )

    def get_by_name(self, name: str) -> list[dict[str, Any]]:
        return self._gw.request(
            "tournaments", "search_by_name", {"name": name}
        )

    def get_by_location(self, location: str) -> list[dict[str, Any]]:
        return self._gw.request(
            "tournaments", "search_by_location", {"location": location}
        )

    def get_active_tournaments(self) -> list[dict[str, Any]]:
        return self._gw.request("tournaments", "list_active")

    def get_upcoming(self) -> list[dict[str, Any]]:
        return self._gw.request("tournaments", "list_upcoming")

    def add_tatami_to_tournament(
        self,
        tournament_id: int,
        name: str,
        mat_number: int | None = None,
        area_size: float | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        return self._gw.request(
            "tournaments",
            "add_tatami",
            {
                "tournament_id": tournament_id,
                "name": name,
                "mat_number": mat_number,
                "area_size": area_size,
                "is_active": is_active,
            },
        )

    def list_tatamis(self, tournament_id: int) -> list[dict[str, Any]]:
        return self._gw.request(
            "tournaments", "list_tatamis", {"tournament_id": tournament_id}
        )


class _CategoryProxy:
    def __init__(self, gw: ServerGateway) -> None:
        self._gw = gw

    def list_all(self) -> list[dict[str, Any]]:
        return self._gw.request("categories", "list")

    def get(self, category_id: int) -> dict[str, Any] | None:
        return self._gw.get_or_none(
            "categories", "get", {"category_id": category_id}
        )

    def create(self, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request("categories", "create", kwargs)

    def update(self, category_id: int, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request(
            "categories", "update", {"category_id": category_id, **kwargs}
        )

    def delete(self, category_id: int) -> None:
        self._gw.request("categories", "delete", {"category_id": category_id})

    def get_by_name(self, name: str) -> list[dict[str, Any]]:
        return self._gw.request("categories", "search_by_name", {"name": name})

    def get_by_belt_level(self, belt_level: str) -> list[dict[str, Any]]:
        return self._gw.request(
            "categories", "search_by_belt_level", {"belt_level": belt_level}
        )

    def get_by_gender(self, gender: str) -> list[dict[str, Any]]:
        return self._gw.request(
            "categories", "search_by_gender", {"gender": gender}
        )

    def get_by_weight_range(
        self,
        min_kg: float | None = None,
        max_kg: float | None = None,
    ) -> list[dict[str, Any]]:
        return self._gw.request(
            "categories",
            "search_by_weight_range",
            {"min_kg": min_kg, "max_kg": max_kg},
        )


class _MatchProxy:
    def __init__(self, gw: ServerGateway) -> None:
        self._gw = gw

    def list_all(self) -> list[dict[str, Any]]:
        return self._gw.request("matches", "list")

    def get(self, match_id: int) -> dict[str, Any] | None:
        return self._gw.get_or_none("matches", "get", {"match_id": match_id})

    def create(self, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request("matches", "create", kwargs)

    def update(self, match_id: int, **kwargs: Any) -> dict[str, Any]:
        return self._gw.request(
            "matches", "update", {"match_id": match_id, **kwargs}
        )

    def delete(self, match_id: int) -> None:
        self._gw.request("matches", "delete", {"match_id": match_id})

    def get_by_tournament(self, tournament_id: int) -> list[dict[str, Any]]:
        return self._gw.request(
            "matches", "get_by_tournament", {"tournament_id": tournament_id}
        )

    def get_by_fighter(self, fighter_id: int) -> dict[str, Any]:
        return self._gw.request(
            "matches", "get_by_fighter", {"fighter_id": fighter_id}
        )

    def get_by_category(self, category_id: int) -> list[dict[str, Any]]:
        return self._gw.request(
            "matches", "get_by_category", {"category_id": category_id}
        )

    def get_by_round(
        self, tournament_id: int, round_number: int
    ) -> list[dict[str, Any]]:
        return self._gw.request(
            "matches",
            "get_by_round",
            {"tournament_id": tournament_id, "round_number": round_number},
        )

    def get_wins_by_fighter(self, fighter_id: int) -> list[dict[str, Any]]:
        return self._gw.request(
            "matches", "get_wins_by_fighter", {"fighter_id": fighter_id}
        )


class _RegistrationProxy:
    def __init__(self, gw: ServerGateway) -> None:
        self._gw = gw

    def list_all(self) -> list[dict[str, Any]]:
        return self._gw.request("registrations", "list")

    def get(self, pk: tuple[int, int, int]) -> dict[str, Any] | None:
        fighter_id, category_id, tournament_id = pk
        return self._gw.get_or_none(
            "registrations",
            "get",
            {
                "fighter_id": fighter_id,
                "category_id": category_id,
                "tournament_id": tournament_id,
            },
        )

    def get_by_tournament(self, tournament_id: int) -> list[dict[str, Any]]:
        return self._gw.request(
            "registrations",
            "list_by_tournament",
            {"tournament_id": tournament_id},
        )

    def get_by_fighter(self, fighter_id: int) -> list[dict[str, Any]]:
        return self._gw.request(
            "registrations", "list_by_fighter", {"fighter_id": fighter_id}
        )

    def get_pending_approvals(
        self, tournament_id: int
    ) -> list[dict[str, Any]]:
        return self._gw.request(
            "registrations",
            "list_pending_approvals",
            {"tournament_id": tournament_id},
        )

    def add(self, reg: dict[str, Any]) -> dict[str, Any]:
        return self._gw.request("registrations", "create", reg)

    def update(self, reg: dict[str, Any]) -> dict[str, Any]:
        return self._gw.request("registrations", "update", reg)

    def delete(self, reg: dict[str, Any]) -> None:
        self._gw.request("registrations", "delete", reg)
