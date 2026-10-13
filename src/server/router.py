"""
router.py — maps (resource, action) pairs to the correct service method.

The Router is stateless; it receives a validated request dict, delegates
to the appropriate service, and returns a response dict ready for the wire.

Supported actions per resource
--------------------------------
fighters:
    list, list_paginated, get, create, update, delete,
    search_by_last_name, search_by_belt_level, search_by_country,
    search_by_email, upsert_medical_record, approve_registration

tournaments:
    list, get, create, update, delete,
    search_by_name, search_by_location, list_active, list_upcoming,
    add_tatami, list_tatamis

categories:
    list, get, create, update, delete,
    search_by_name, search_by_belt_level, search_by_gender,
    search_by_weight_range

matches:
    list, get, create, update, delete,
    get_by_tournament, get_by_fighter, get_by_category,
    get_by_round, get_wins_by_fighter

registrations:
    list, get, list_by_tournament, list_by_fighter,
    list_pending_approvals, create, update, approve, delete
"""

from __future__ import annotations

from typing import Any

from src.server import protocol
from src.server.services import (
    FighterService,
    TournamentService,
    CategoryService,
    MatchService,
    RegistrationService,
)


class Router:
    """Receives request dicts, dispatches to service methods, returns responses."""

    def __init__(self, session_factory) -> None:
        self._fighters = FighterService(session_factory)
        self._tournaments = TournamentService(session_factory)
        self._categories = CategoryService(session_factory)
        self._matches = MatchService(session_factory)
        self._registrations = RegistrationService(session_factory)

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dispatch *request* and return a protocol-ready response envelope."""
        resource = request.get("resource", "")
        action = request.get("action", "")
        payload = request.get("payload") or {}

        try:
            data = self._dispatch(resource, action, payload)
            return protocol.ok(data)
        except ValueError as exc:
            return protocol.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            return protocol.error(f"Internal server error: {exc}")

    # ── Dispatcher ─────────────────────────────────────────────────────────────

    def _dispatch(
        self, resource: str, action: str, payload: dict[str, Any]
    ) -> Any:
        handlers = {
            "fighters": self._handle_fighters,
            "tournaments": self._handle_tournaments,
            "categories": self._handle_categories,
            "matches": self._handle_matches,
            "registrations": self._handle_registrations,
        }
        handler = handlers.get(resource)
        if handler is None:
            raise ValueError(f"Unknown resource: '{resource}'.")
        return handler(action, payload)

    # ── Per-resource handlers ──────────────────────────────────────────────────

    def _handle_fighters(
        self, action: str, payload: dict[str, Any]
    ) -> Any:
        svc = self._fighters
        match action:
            case "list":
                return svc.list_all()
            case "list_paginated":
                return svc.list_paginated(
                    page=payload.get("page", 1),
                    page_size=payload.get("page_size", 10),
                )
            case "get":
                fid = _require_int(payload, "fighter_id")
                result = svc.get_by_id(fid)
                if result is None:
                    raise ValueError(f"Fighter with id={fid} not found.")
                return result
            case "create":
                return svc.create(payload)
            case "update":
                fid = _require_int(payload, "fighter_id")
                return svc.update(fid, payload)
            case "delete":
                fid = _require_int(payload, "fighter_id")
                svc.delete(fid)
                return {"deleted": fid}
            case "search_by_last_name":
                return svc.search_by_last_name(payload.get("last_name", ""))
            case "search_by_belt_level":
                return svc.search_by_belt_level(payload.get("belt_level", ""))
            case "search_by_country":
                return svc.search_by_country(payload.get("country", ""))
            case "search_by_email":
                return svc.search_by_email(payload.get("email", ""))
            case "upsert_medical_record":
                fid = _require_int(payload, "fighter_id")
                return svc.upsert_medical_record(fid, payload)
            case "approve_registration":
                fid = _require_int(payload, "fighter_id")
                cid = _require_int(payload, "category_id")
                tid = _require_int(payload, "tournament_id")
                return svc.approve_registration(fid, cid, tid)
            case _:
                raise ValueError(
                    f"Unknown action '{action}' for resource 'fighters'."
                )

    def _handle_tournaments(
        self, action: str, payload: dict[str, Any]
    ) -> Any:
        svc = self._tournaments
        match action:
            case "list":
                return svc.list_all()
            case "get":
                tid = _require_int(payload, "tournament_id")
                result = svc.get_by_id(tid)
                if result is None:
                    raise ValueError(f"Tournament with id={tid} not found.")
                return result
            case "create":
                return svc.create(payload)
            case "update":
                tid = _require_int(payload, "tournament_id")
                return svc.update(tid, payload)
            case "delete":
                tid = _require_int(payload, "tournament_id")
                svc.delete(tid)
                return {"deleted": tid}
            case "search_by_name":
                return svc.search_by_name(payload.get("name", ""))
            case "search_by_location":
                return svc.search_by_location(payload.get("location", ""))
            case "list_active":
                return svc.list_active()
            case "list_upcoming":
                return svc.list_upcoming()
            case "add_tatami":
                tid = _require_int(payload, "tournament_id")
                return svc.add_tatami(tid, payload)
            case "list_tatamis":
                tid = _require_int(payload, "tournament_id")
                return svc.list_tatamis(tid)
            case _:
                raise ValueError(
                    f"Unknown action '{action}' for resource 'tournaments'."
                )

    def _handle_categories(
        self, action: str, payload: dict[str, Any]
    ) -> Any:
        svc = self._categories
        match action:
            case "list":
                return svc.list_all()
            case "get":
                cid = _require_int(payload, "category_id")
                result = svc.get_by_id(cid)
                if result is None:
                    raise ValueError(f"Category with id={cid} not found.")
                return result
            case "create":
                return svc.create(payload)
            case "update":
                cid = _require_int(payload, "category_id")
                return svc.update(cid, payload)
            case "delete":
                cid = _require_int(payload, "category_id")
                svc.delete(cid)
                return {"deleted": cid}
            case "search_by_name":
                return svc.search_by_name(payload.get("name", ""))
            case "search_by_belt_level":
                return svc.search_by_belt_level(payload.get("belt_level", ""))
            case "search_by_gender":
                return svc.search_by_gender(payload.get("gender", ""))
            case "search_by_weight_range":
                return svc.search_by_weight_range(
                    min_kg=payload.get("min_kg"),
                    max_kg=payload.get("max_kg"),
                )
            case _:
                raise ValueError(
                    f"Unknown action '{action}' for resource 'categories'."
                )

    def _handle_matches(
        self, action: str, payload: dict[str, Any]
    ) -> Any:
        svc = self._matches
        match action:
            case "list":
                return svc.list_all()
            case "get":
                mid = _require_int(payload, "match_id")
                result = svc.get_by_id(mid)
                if result is None:
                    raise ValueError(f"Match with id={mid} not found.")
                return result
            case "create":
                return svc.create(payload)
            case "update":
                mid = _require_int(payload, "match_id")
                return svc.update(mid, payload)
            case "delete":
                mid = _require_int(payload, "match_id")
                svc.delete(mid)
                return {"deleted": mid}
            case "get_by_tournament":
                return svc.get_by_tournament(
                    _require_int(payload, "tournament_id")
                )
            case "get_by_fighter":
                return svc.get_by_fighter(
                    _require_int(payload, "fighter_id")
                )
            case "get_by_category":
                return svc.get_by_category(
                    _require_int(payload, "category_id")
                )
            case "get_by_round":
                return svc.get_by_round(
                    _require_int(payload, "tournament_id"),
                    _require_int(payload, "round_number"),
                )
            case "get_wins_by_fighter":
                return svc.get_wins_by_fighter(
                    _require_int(payload, "fighter_id")
                )
            case _:
                raise ValueError(
                    f"Unknown action '{action}' for resource 'matches'."
                )

    def _handle_registrations(
        self, action: str, payload: dict[str, Any]
    ) -> Any:
        svc = self._registrations
        match action:
            case "list":
                return svc.list_all()
            case "get":
                return _reg_or_404(
                    svc.get(
                        _require_int(payload, "fighter_id"),
                        _require_int(payload, "category_id"),
                        _require_int(payload, "tournament_id"),
                    )
                )
            case "list_by_tournament":
                return svc.list_by_tournament(
                    _require_int(payload, "tournament_id")
                )
            case "list_by_fighter":
                return svc.list_by_fighter(_require_int(payload, "fighter_id"))
            case "list_pending_approvals":
                return svc.list_pending_approvals(
                    _require_int(payload, "tournament_id")
                )
            case "create":
                return svc.create(payload)
            case "update":
                return svc.update(payload)
            case "approve":
                return svc.approve(
                    _require_int(payload, "fighter_id"),
                    _require_int(payload, "category_id"),
                    _require_int(payload, "tournament_id"),
                )
            case "delete":
                svc.delete(
                    _require_int(payload, "fighter_id"),
                    _require_int(payload, "category_id"),
                    _require_int(payload, "tournament_id"),
                )
                return {"deleted": True}
            case _:
                raise ValueError(
                    f"Unknown action '{action}' for resource 'registrations'."
                )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_int(payload: dict[str, Any], key: str) -> int:
    """Extract a required integer from *payload*, raising ValueError if absent."""
    value = payload.get(key)
    if value is None:
        raise ValueError(f"Missing required field: '{key}'.")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Field '{key}' must be an integer.")


def _reg_or_404(result: dict[str, Any] | None) -> dict[str, Any]:
    if result is None:
        raise ValueError("Registration not found.")
    return result
