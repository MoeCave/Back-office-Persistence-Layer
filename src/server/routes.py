"""Declarative routing table: (resource, action) -> handler.

Each handler receives the resource's service and the request payload.
The small factories below build the handlers so that no routing logic
is repeated.  The table is the single source of truth for the operations
listed in ``docs/PROTOCOL.md``.
"""

from __future__ import annotations

from typing import Any, Callable

from src.server.errors import NotFoundError
from src.server.validation import (
    clean_str,
    optional_number,
    pagination,
    require_int,
)

Handler = Callable[[Any, dict[str, Any]], Any]


# -- Handler factories -------------------------------------------------


def _call(method: str, *id_keys: str) -> Handler:
    """Call ``service.method`` with the required integer ids."""

    def handler(service, payload):
        args = [require_int(payload, key) for key in id_keys]
        return getattr(service, method)(*args)

    return handler


def _call_with_payload(method: str) -> Handler:
    """Call ``service.method(payload)``."""

    def handler(service, payload):
        return getattr(service, method)(payload)

    return handler


def _call_with_id_and_payload(method: str, id_key: str) -> Handler:
    """Call ``service.method(entity_id, payload)``."""

    def handler(service, payload):
        return getattr(service, method)(require_int(payload, id_key), payload)

    return handler


def _search(method: str, key: str) -> Handler:
    """Call ``service.method(text)`` with a cleaned string."""

    def handler(service, payload):
        return getattr(service, method)(clean_str(payload.get(key)))

    return handler


def _get_one(label: str, *id_keys: str, method: str = "get_by_id") -> Handler:
    """Fetch one entity and raise NotFoundError when it is missing."""

    def handler(service, payload):
        ids = [require_int(payload, key) for key in id_keys]
        result = getattr(service, method)(*ids)
        if result is None:
            if len(ids) == 1:
                raise NotFoundError(f"{label} with id={ids[0]} not found.")
            raise NotFoundError(f"{label} not found.")
        return result

    return handler


def _delete(*id_keys: str) -> Handler:
    """Delete an entity; answer ``{"deleted": id}`` or ``True``."""

    def handler(service, payload):
        ids = [require_int(payload, key) for key in id_keys]
        service.delete(*ids)
        return {"deleted": ids[0] if len(ids) == 1 else True}

    return handler


def _list_paginated(service, payload):
    page, page_size = pagination(payload)
    return service.list_paginated(page=page, page_size=page_size)


def _weight_range(service, payload):
    return service.search_by_weight_range(
        min_kg=optional_number(payload, "min_kg"),
        max_kg=optional_number(payload, "max_kg"),
    )


def _get_by_round(service, payload):
    return service.get_by_round(
        require_int(payload, "tournament_id"),
        require_int(payload, "round_number"),
    )


_LIST: Handler = _call("list_all")
_REGISTRATION_KEY = ("fighter_id", "category_id", "tournament_id")

# -- Routing table -----------------------------------------------------

ROUTES: dict[str, dict[str, Handler]] = {
    "fighters": {
        "list": _LIST,
        "list_paginated": _list_paginated,
        "get": _get_one("Fighter", "fighter_id"),
        "create": _call_with_payload("create"),
        "update": _call_with_id_and_payload("update", "fighter_id"),
        "delete": _delete("fighter_id"),
        "search_by_last_name": _search("search_by_last_name", "last_name"),
        "search_by_belt_level": _search("search_by_belt_level", "belt_level"),
        "search_by_country": _search("search_by_country", "country"),
        "search_by_email": _search("search_by_email", "email"),
        "upsert_medical_record": _call_with_id_and_payload(
            "upsert_medical_record", "fighter_id"
        ),
        "approve_registration": _call(
            "approve_registration", *_REGISTRATION_KEY
        ),
    },
    "tournaments": {
        "list": _LIST,
        "get": _get_one("Tournament", "tournament_id"),
        "create": _call_with_payload("create"),
        "update": _call_with_id_and_payload("update", "tournament_id"),
        "delete": _delete("tournament_id"),
        "search_by_name": _search("search_by_name", "name"),
        "search_by_location": _search("search_by_location", "location"),
        "list_active": _call("list_active"),
        "list_upcoming": _call("list_upcoming"),
        "add_tatami": _call_with_id_and_payload("add_tatami", "tournament_id"),
        "list_tatamis": _call("list_tatamis", "tournament_id"),
    },
    "categories": {
        "list": _LIST,
        "get": _get_one("Category", "category_id"),
        "create": _call_with_payload("create"),
        "update": _call_with_id_and_payload("update", "category_id"),
        "delete": _delete("category_id"),
        "search_by_name": _search("search_by_name", "name"),
        "search_by_belt_level": _search("search_by_belt_level", "belt_level"),
        "search_by_gender": _search("search_by_gender", "gender"),
        "search_by_weight_range": _weight_range,
    },
    "matches": {
        "list": _LIST,
        "get": _get_one("Match", "match_id"),
        "create": _call_with_payload("create"),
        "update": _call_with_id_and_payload("update", "match_id"),
        "delete": _delete("match_id"),
        "get_by_tournament": _call("get_by_tournament", "tournament_id"),
        "get_by_fighter": _call("get_by_fighter", "fighter_id"),
        "get_by_category": _call("get_by_category", "category_id"),
        "get_by_round": _get_by_round,
        "get_wins_by_fighter": _call("get_wins_by_fighter", "fighter_id"),
    },
    "registrations": {
        "list": _LIST,
        "get": _get_one("Registration", *_REGISTRATION_KEY, method="get"),
        "list_by_tournament": _call("list_by_tournament", "tournament_id"),
        "list_by_fighter": _call("list_by_fighter", "fighter_id"),
        "list_pending_approvals": _call(
            "list_pending_approvals", "tournament_id"
        ),
        "create": _call_with_payload("create"),
        "update": _call_with_payload("update"),
        "approve": _call("approve", *_REGISTRATION_KEY),
        "delete": _delete(*_REGISTRATION_KEY),
    },
}
