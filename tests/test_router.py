"""
test_router.py — unit tests for src/server/router.py.

The Router is tested by injecting mock service objects so no real database
or socket is needed.  Each test verifies that:
  - the correct service method is called with the correct arguments
  - the response envelope is well-formed (success / error)
  - unknown resource / action produce error envelopes
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.server.router import Router

# ── Fixtures ─────────────────────────────────────────────────────────────────

FIGHTER_DICT = {
    "fighter_id": 1,
    "first_name": "Ana",
    "last_name": "García",
    "gender": "F",
    "belt_level": "blue",
    "club_name": "Club BCN",
    "country": "Spain",
    "email": "ana@example.com",
    "phone": None,
    "birth_date": None,
    "created_at": "2026-01-01T00:00:00",
}

TOURNAMENT_DICT = {
    "tournament_id": 1,
    "name": "Copa Primavera",
    "location": "Barcelona",
    "start_date": "2026-06-01",
    "end_date": "2026-06-02",
    "max_fighters": 64,
    "created_at": "2026-01-01T00:00:00",
}

CATEGORY_DICT = {
    "category_id": 1,
    "name": "Blue -70kg F",
    "belt_level": "blue",
    "weight_min_kg": 57.0,
    "weight_max_kg": 70.0,
    "gender": "F",
}

MATCH_DICT = {
    "match_id": 1,
    "tournament_id": 1,
    "category_id": 1,
    "blue_fighter_id": 1,
    "red_fighter_id": 2,
    "winner_id": 1,
    "round_number": 1,
    "duration_seconds": 185.0,
    "win_method": "ippon",
    "scheduled_time": None,
}

REGISTRATION_DICT = {
    "fighter_id": 1,
    "category_id": 1,
    "tournament_id": 1,
    "weight_in_weight_kg": 68.5,
    "registration_date": "2026-01-10T00:00:00",
    "is_approved": False,
    "last_update": None,
}


@pytest.fixture
def mock_session_factory():
    """Return a dummy session factory (never called in these tests)."""
    return MagicMock()


@pytest.fixture
def router_with_mocks(mock_session_factory):
    """
    Build a Router whose internal service instances are replaced by Mocks.
    Returns (router, mocks_dict).
    """
    router = Router(mock_session_factory)

    mocks = {
        "fighters": MagicMock(),
        "tournaments": MagicMock(),
        "categories": MagicMock(),
        "matches": MagicMock(),
        "registrations": MagicMock(),
    }
    router._fighters = mocks["fighters"]
    router._tournaments = mocks["tournaments"]
    router._categories = mocks["categories"]
    router._matches = mocks["matches"]
    router._registrations = mocks["registrations"]

    return router, mocks


# ── Fighter actions ──────────────────────────────────────────────────────────


class TestRouterFighters:
    def test_list_fighters(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].list_all.return_value = [FIGHTER_DICT]

        resp = router.handle(
            {"resource": "fighters", "action": "list", "payload": {}}
        )

        assert resp["success"] is True
        assert resp["data"] == [FIGHTER_DICT]
        mocks["fighters"].list_all.assert_called_once()

    def test_get_fighter_found(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].get_by_id.return_value = FIGHTER_DICT

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "get",
                "payload": {"fighter_id": 1},
            }
        )

        assert resp["success"] is True
        assert resp["data"]["fighter_id"] == 1
        mocks["fighters"].get_by_id.assert_called_once_with(1)

    def test_get_fighter_not_found(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].get_by_id.return_value = None

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "get",
                "payload": {"fighter_id": 999},
            }
        )

        assert resp["success"] is False
        assert "not found" in resp["error"].lower()

    def test_create_fighter(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].create.return_value = FIGHTER_DICT

        payload = {"first_name": "Ana", "last_name": "García"}
        resp = router.handle(
            {
                "resource": "fighters",
                "action": "create",
                "payload": payload,
            }
        )

        assert resp["success"] is True
        mocks["fighters"].create.assert_called_once_with(payload)

    def test_update_fighter(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].update.return_value = FIGHTER_DICT

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "update",
                "payload": {"fighter_id": 1, "belt_level": "black"},
            }
        )

        assert resp["success"] is True
        mocks["fighters"].update.assert_called_once()

    def test_delete_fighter(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].delete.return_value = None

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "delete",
                "payload": {"fighter_id": 1},
            }
        )

        assert resp["success"] is True
        assert resp["data"]["deleted"] == 1

    def test_list_paginated(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].list_paginated.return_value = {
            "total": 1,
            "page": 1,
            "page_size": 10,
            "items": [FIGHTER_DICT],
        }

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "list_paginated",
                "payload": {"page": 1, "page_size": 10},
            }
        )

        assert resp["success"] is True
        mocks["fighters"].list_paginated.assert_called_once_with(
            page=1, page_size=10
        )

    def test_search_by_last_name(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].search_by_last_name.return_value = [FIGHTER_DICT]

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "search_by_last_name",
                "payload": {"last_name": "García"},
            }
        )

        assert resp["success"] is True
        mocks["fighters"].search_by_last_name.assert_called_once_with("García")

    def test_upsert_medical_record(self, router_with_mocks):
        router, mocks = router_with_mocks
        mr = {"medical_record_id": 1, "fighter_id": 1, "blood_type": "A+"}
        mocks["fighters"].upsert_medical_record.return_value = mr

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "upsert_medical_record",
                "payload": {"fighter_id": 1, "blood_type": "A+"},
            }
        )

        assert resp["success"] is True
        mocks["fighters"].upsert_medical_record.assert_called_once()

    def test_approve_registration(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].approve_registration.return_value = REGISTRATION_DICT

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "approve_registration",
                "payload": {
                    "fighter_id": 1,
                    "category_id": 1,
                    "tournament_id": 1,
                },
            }
        )

        assert resp["success"] is True
        mocks["fighters"].approve_registration.assert_called_once_with(1, 1, 1)

    def test_missing_fighter_id_returns_error(self, router_with_mocks):
        router, _ = router_with_mocks
        resp = router.handle(
            {
                "resource": "fighters",
                "action": "get",
                "payload": {},  # fighter_id omitted
            }
        )
        assert resp["success"] is False

    def test_unknown_action_returns_error(self, router_with_mocks):
        router, _ = router_with_mocks
        resp = router.handle(
            {
                "resource": "fighters",
                "action": "fly_to_moon",
                "payload": {},
            }
        )
        assert resp["success"] is False


# ── Tournament actions ───────────────────────────────────────────────────────


class TestRouterTournaments:
    def test_list_tournaments(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["tournaments"].list_all.return_value = [TOURNAMENT_DICT]

        resp = router.handle(
            {"resource": "tournaments", "action": "list", "payload": {}}
        )

        assert resp["success"] is True
        assert len(resp["data"]) == 1

    def test_get_tournament_found(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["tournaments"].get_by_id.return_value = TOURNAMENT_DICT

        resp = router.handle(
            {
                "resource": "tournaments",
                "action": "get",
                "payload": {"tournament_id": 1},
            }
        )

        assert resp["success"] is True

    def test_create_tournament(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["tournaments"].create.return_value = TOURNAMENT_DICT

        resp = router.handle(
            {
                "resource": "tournaments",
                "action": "create",
                "payload": {"name": "Copa Primavera"},
            }
        )

        assert resp["success"] is True

    def test_add_tatami(self, router_with_mocks):
        router, mocks = router_with_mocks
        tatami = {
            "tatami_id": 1,
            "tournament_id": 1,
            "name": "Tatami A",
            "mat_number": 1,
            "area_size": 64.0,
            "is_active": True,
        }
        mocks["tournaments"].add_tatami.return_value = tatami

        resp = router.handle(
            {
                "resource": "tournaments",
                "action": "add_tatami",
                "payload": {"tournament_id": 1, "name": "Tatami A"},
            }
        )

        assert resp["success"] is True

    def test_list_active(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["tournaments"].list_active.return_value = [TOURNAMENT_DICT]

        resp = router.handle(
            {"resource": "tournaments", "action": "list_active", "payload": {}}
        )

        assert resp["success"] is True


# ── Category actions ─────────────────────────────────────────────────────────


class TestRouterCategories:
    def test_list_categories(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["categories"].list_all.return_value = [CATEGORY_DICT]

        resp = router.handle(
            {"resource": "categories", "action": "list", "payload": {}}
        )

        assert resp["success"] is True

    def test_search_by_weight_range(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["categories"].search_by_weight_range.return_value = [
            CATEGORY_DICT
        ]

        resp = router.handle(
            {
                "resource": "categories",
                "action": "search_by_weight_range",
                "payload": {"min_kg": 50.0, "max_kg": 70.0},
            }
        )

        assert resp["success"] is True
        mocks["categories"].search_by_weight_range.assert_called_once_with(
            min_kg=50.0, max_kg=70.0
        )


# ── Match actions ────────────────────────────────────────────────────────────


class TestRouterMatches:
    def test_list_matches(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["matches"].list_all.return_value = [MATCH_DICT]

        resp = router.handle(
            {"resource": "matches", "action": "list", "payload": {}}
        )

        assert resp["success"] is True

    def test_get_by_fighter(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["matches"].get_by_fighter.return_value = {
            "matches": [MATCH_DICT],
            "total_wins": 1,
        }

        resp = router.handle(
            {
                "resource": "matches",
                "action": "get_by_fighter",
                "payload": {"fighter_id": 1},
            }
        )

        assert resp["success"] is True

    def test_get_by_round(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["matches"].get_by_round.return_value = [MATCH_DICT]

        resp = router.handle(
            {
                "resource": "matches",
                "action": "get_by_round",
                "payload": {"tournament_id": 1, "round_number": 1},
            }
        )

        assert resp["success"] is True
        mocks["matches"].get_by_round.assert_called_once_with(1, 1)


# ── Registration actions ─────────────────────────────────────────────────────


class TestRouterRegistrations:
    def test_create_registration(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["registrations"].create.return_value = REGISTRATION_DICT

        resp = router.handle(
            {
                "resource": "registrations",
                "action": "create",
                "payload": {
                    "fighter_id": 1,
                    "category_id": 1,
                    "tournament_id": 1,
                },
            }
        )

        assert resp["success"] is True

    def test_get_registration_found(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["registrations"].get.return_value = REGISTRATION_DICT

        resp = router.handle(
            {
                "resource": "registrations",
                "action": "get",
                "payload": {
                    "fighter_id": 1,
                    "category_id": 1,
                    "tournament_id": 1,
                },
            }
        )

        assert resp["success"] is True

    def test_get_registration_not_found(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["registrations"].get.return_value = None

        resp = router.handle(
            {
                "resource": "registrations",
                "action": "get",
                "payload": {
                    "fighter_id": 99,
                    "category_id": 1,
                    "tournament_id": 1,
                },
            }
        )

        assert resp["success"] is False

    def test_delete_registration(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["registrations"].delete.return_value = None

        resp = router.handle(
            {
                "resource": "registrations",
                "action": "delete",
                "payload": {
                    "fighter_id": 1,
                    "category_id": 1,
                    "tournament_id": 1,
                },
            }
        )

        assert resp["success"] is True
        assert resp["data"]["deleted"] is True


# ── Unknown resource ─────────────────────────────────────────────────────────


class TestRouterUnknownResource:
    def test_unknown_resource(self, router_with_mocks):
        router, _ = router_with_mocks
        resp = router.handle(
            {"resource": "unicorns", "action": "list", "payload": {}}
        )
        assert resp["success"] is False

    def test_service_raises_value_error(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].create.side_effect = ValueError(
            "first_name required"
        )

        resp = router.handle(
            {
                "resource": "fighters",
                "action": "create",
                "payload": {},
            }
        )

        assert resp["success"] is False
        assert "first_name" in resp["error"]

    def test_service_raises_unexpected_exception(self, router_with_mocks):
        router, mocks = router_with_mocks
        mocks["fighters"].list_all.side_effect = RuntimeError("DB exploded")

        resp = router.handle(
            {"resource": "fighters", "action": "list", "payload": {}}
        )

        assert resp["success"] is False
        assert "Internal server error" in resp["error"]
