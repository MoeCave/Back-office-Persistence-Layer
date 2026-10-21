"""
test_services.py — unit tests for CategoryService, TournamentService,
MatchService, and RegistrationService.

Uses in-memory SQLite via the shared conftest fixtures.
"""

from __future__ import annotations

import pytest

from src.server.services import (
    CategoryService,
    FighterService,
    MatchService,
    RegistrationService,
    TournamentService,
)

# ── CategoryService ──────────────────────────────────────────────────────────


class TestCategoryService:
    def test_create_category(self, session_factory):
        svc = CategoryService(session_factory)
        cat = svc.create(
            {
                "name": "Blue -70kg F",
                "belt_level": "blue",
                "gender": "F",
                "weight_min_kg": 57.0,
                "weight_max_kg": 70.0,
            }
        )
        assert cat["name"] == "Blue -70kg F"
        assert isinstance(cat["category_id"], int)

    def test_create_missing_name_raises(self, session_factory):
        svc = CategoryService(session_factory)
        with pytest.raises(ValueError, match="name"):
            svc.create({"belt_level": "blue"})

    def test_list_all(self, session_factory):
        svc = CategoryService(session_factory)
        svc.create({"name": "Cat A"})
        svc.create({"name": "Cat B"})
        results = svc.list_all()
        names = {r["name"] for r in results}
        assert "Cat A" in names
        assert "Cat B" in names

    def test_get_by_id_found(self, session_factory):
        svc = CategoryService(session_factory)
        created = svc.create({"name": "Gold Cat"})
        found = svc.get_by_id(created["category_id"])
        assert found is not None
        assert found["name"] == "Gold Cat"

    def test_get_by_id_not_found(self, session_factory):
        svc = CategoryService(session_factory)
        assert svc.get_by_id(999999) is None

    def test_update_category(self, session_factory):
        svc = CategoryService(session_factory)
        created = svc.create({"name": "Old Name"})
        updated = svc.update(created["category_id"], {"name": "New Name"})
        assert updated["name"] == "New Name"

    def test_update_nonexistent_raises(self, session_factory):
        svc = CategoryService(session_factory)
        with pytest.raises(ValueError, match="not found"):
            svc.update(999999, {"name": "X"})

    def test_delete_category(self, session_factory):
        svc = CategoryService(session_factory)
        created = svc.create({"name": "Temp Cat"})
        cid = created["category_id"]
        svc.delete(cid)
        assert svc.get_by_id(cid) is None

    def test_delete_nonexistent_raises(self, session_factory):
        svc = CategoryService(session_factory)
        with pytest.raises(ValueError):
            svc.delete(999999)

    def test_search_by_name(self, session_factory):
        svc = CategoryService(session_factory)
        svc.create({"name": "Blue Butterfly"})
        results = svc.search_by_name("Butterfly")
        assert any("Butterfly" in r["name"] for r in results)

    def test_search_by_belt_level(self, session_factory):
        svc = CategoryService(session_factory)
        svc.create({"name": "Black Belt Cat", "belt_level": "black"})
        results = svc.search_by_belt_level("black")
        assert all(r["belt_level"] == "black" for r in results)

    def test_search_by_gender(self, session_factory):
        svc = CategoryService(session_factory)
        svc.create({"name": "Female Cat", "gender": "F"})
        results = svc.search_by_gender("F")
        assert all(r["gender"] == "F" for r in results)

    def test_search_by_weight_range(self, session_factory):
        svc = CategoryService(session_factory)
        svc.create(
            {"name": "Light Cat", "weight_min_kg": 0.0, "weight_max_kg": 57.0}
        )
        results = svc.search_by_weight_range(max_kg=57.0)
        assert any(r["name"] == "Light Cat" for r in results)

    def test_get_by_id_includes_relationship_counts(self, session_factory):
        svc = CategoryService(session_factory)
        created = svc.create({"name": "Count Cat"})
        result = svc.get_by_id(created["category_id"])
        assert "total_registrations" in result
        assert "total_matches" in result


# ── TournamentService ────────────────────────────────────────────────────────


class TestTournamentService:
    def test_create_tournament(self, session_factory):
        svc = TournamentService(session_factory)
        t = svc.create(
            {
                "name": "Copa Test",
                "location": "Barcelona",
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
                "max_fighters": 32,
            }
        )
        assert t["name"] == "Copa Test"
        assert isinstance(t["tournament_id"], int)

    def test_create_missing_name_raises(self, session_factory):
        svc = TournamentService(session_factory)
        with pytest.raises(ValueError, match="name"):
            svc.create({"location": "BCN"})

    def test_list_all(self, session_factory):
        svc = TournamentService(session_factory)
        svc.create({"name": "T1"})
        svc.create({"name": "T2"})
        results = svc.list_all()
        names = {r["name"] for r in results}
        assert "T1" in names and "T2" in names

    def test_get_by_id_found(self, session_factory):
        svc = TournamentService(session_factory)
        created = svc.create({"name": "FindMe"})
        found = svc.get_by_id(created["tournament_id"])
        assert found is not None
        assert found["name"] == "FindMe"

    def test_get_by_id_includes_counts(self, session_factory):
        svc = TournamentService(session_factory)
        created = svc.create({"name": "Counts Tourney"})
        result = svc.get_by_id(created["tournament_id"])
        assert "total_matches" in result
        assert "total_registrations" in result
        assert "pending_registrations" in result
        assert "tatamis" in result

    def test_update_tournament(self, session_factory):
        svc = TournamentService(session_factory)
        created = svc.create({"name": "Old Name"})
        updated = svc.update(created["tournament_id"], {"name": "New Name"})
        assert updated["name"] == "New Name"

    def test_delete_tournament(self, session_factory):
        svc = TournamentService(session_factory)
        created = svc.create({"name": "Deletable"})
        tid = created["tournament_id"]
        svc.delete(tid)
        assert svc.get_by_id(tid) is None

    def test_search_by_name(self, session_factory):
        svc = TournamentService(session_factory)
        svc.create({"name": "Spring Open"})
        results = svc.search_by_name("Spring")
        assert any("Spring" in r["name"] for r in results)

    def test_search_by_location(self, session_factory):
        svc = TournamentService(session_factory)
        svc.create({"name": "Madrid Cup", "location": "Madrid"})
        results = svc.search_by_location("Madrid")
        assert any(r.get("location") == "Madrid" for r in results)

    def test_add_tatami(self, session_factory):
        svc = TournamentService(session_factory)
        created = svc.create({"name": "Tatami Tourney"})
        tatami = svc.add_tatami(
            created["tournament_id"],
            {
                "name": "Tatami A",
                "mat_number": 1,
                "area_size": 64.0,
                "is_active": True,
            },
        )
        assert tatami["name"] == "Tatami A"
        assert tatami["tournament_id"] == created["tournament_id"]

    def test_add_tatami_missing_name_raises(self, session_factory):
        svc = TournamentService(session_factory)
        created = svc.create({"name": "T"})
        with pytest.raises(ValueError, match="Tatami name"):
            svc.add_tatami(created["tournament_id"], {"name": ""})

    def test_list_tatamis(self, session_factory):
        svc = TournamentService(session_factory)
        created = svc.create({"name": "Many Tatami"})
        tid = created["tournament_id"]
        svc.add_tatami(tid, {"name": "T1"})
        svc.add_tatami(tid, {"name": "T2"})
        tatamis = svc.list_tatamis(tid)
        assert len(tatamis) >= 2

    def test_list_active_returns_list(self, session_factory):
        svc = TournamentService(session_factory)
        results = svc.list_active()
        assert isinstance(results, list)

    def test_list_upcoming_returns_list(self, session_factory):
        svc = TournamentService(session_factory)
        results = svc.list_upcoming()
        assert isinstance(results, list)


# ── MatchService ─────────────────────────────────────────────────────────────


class TestMatchService:
    @pytest.fixture
    def tournament_id(self, session_factory):
        svc = TournamentService(session_factory)
        t = svc.create({"name": "Match Tourney"})
        return t["tournament_id"]

    @pytest.fixture
    def fighter_ids(self, session_factory):
        svc = FighterService(session_factory)
        f1 = svc.create({"first_name": "Blue", "last_name": "Corner"})
        f2 = svc.create({"first_name": "Red", "last_name": "Corner"})
        return f1["fighter_id"], f2["fighter_id"]

    @pytest.fixture
    def category_id(self, session_factory):
        svc = CategoryService(session_factory)
        c = svc.create({"name": "Match Cat"})
        return c["category_id"]

    def test_create_match(self, session_factory, tournament_id, fighter_ids):
        svc = MatchService(session_factory)
        blue_id, red_id = fighter_ids
        match = svc.create(
            {
                "tournament_id": tournament_id,
                "blue_fighter_id": blue_id,
                "red_fighter_id": red_id,
                "round_number": 1,
                "win_method": "ippon",
            }
        )
        assert isinstance(match["match_id"], int)
        assert match["round_number"] == 1

    def test_create_missing_tournament_id_raises(self, session_factory):
        svc = MatchService(session_factory)
        with pytest.raises(ValueError, match="tournament_id"):
            svc.create({"round_number": 1})

    def test_list_all(self, session_factory, tournament_id, fighter_ids):
        svc = MatchService(session_factory)
        blue_id, red_id = fighter_ids
        svc.create(
            {"tournament_id": tournament_id, "blue_fighter_id": blue_id}
        )
        results = svc.list_all()
        assert any(r["tournament_id"] == tournament_id for r in results)

    def test_get_by_id_found(self, session_factory, tournament_id):
        svc = MatchService(session_factory)
        created = svc.create({"tournament_id": tournament_id})
        found = svc.get_by_id(created["match_id"])
        assert found is not None
        assert "fighters_info" in found

    def test_get_by_id_not_found(self, session_factory):
        svc = MatchService(session_factory)
        assert svc.get_by_id(999999) is None

    def test_update_match(self, session_factory, tournament_id, fighter_ids):
        svc = MatchService(session_factory)
        blue_id, _ = fighter_ids
        created = svc.create({"tournament_id": tournament_id})
        updated = svc.update(
            created["match_id"], {"winner_id": blue_id, "win_method": "ippon"}
        )
        assert updated["winner_id"] == blue_id

    def test_delete_match(self, session_factory, tournament_id):
        svc = MatchService(session_factory)
        created = svc.create({"tournament_id": tournament_id})
        mid = created["match_id"]
        svc.delete(mid)
        assert svc.get_by_id(mid) is None

    def test_get_by_tournament(self, session_factory, tournament_id):
        svc = MatchService(session_factory)
        svc.create({"tournament_id": tournament_id, "round_number": 1})
        results = svc.get_by_tournament(tournament_id)
        assert all(r["tournament_id"] == tournament_id for r in results)

    def test_get_by_fighter(self, session_factory, tournament_id, fighter_ids):
        svc = MatchService(session_factory)
        blue_id, red_id = fighter_ids
        svc.create(
            {
                "tournament_id": tournament_id,
                "blue_fighter_id": blue_id,
                "red_fighter_id": red_id,
                "winner_id": blue_id,
            }
        )
        result = svc.get_by_fighter(blue_id)
        assert "matches" in result
        assert "total_wins" in result
        assert result["total_wins"] >= 1

    def test_get_by_round(self, session_factory, tournament_id):
        svc = MatchService(session_factory)
        svc.create({"tournament_id": tournament_id, "round_number": 3})
        results = svc.get_by_round(tournament_id, 3)
        assert all(r["round_number"] == 3 for r in results)

    def test_get_wins_by_fighter(
        self, session_factory, tournament_id, fighter_ids
    ):
        svc = MatchService(session_factory)
        blue_id, red_id = fighter_ids
        svc.create(
            {
                "tournament_id": tournament_id,
                "blue_fighter_id": blue_id,
                "red_fighter_id": red_id,
                "winner_id": blue_id,
            }
        )
        wins = svc.get_wins_by_fighter(blue_id)
        assert all(r["winner_id"] == blue_id for r in wins)


# ── RegistrationService ──────────────────────────────────────────────────────


class TestRegistrationService:
    @pytest.fixture
    def setup_ids(self, session_factory):
        f_svc = FighterService(session_factory)
        c_svc = CategoryService(session_factory)
        t_svc = TournamentService(session_factory)

        fighter = f_svc.create({"first_name": "Reg", "last_name": "Fighter"})
        category = c_svc.create({"name": "Reg Cat"})
        tournament = t_svc.create({"name": "Reg Tourney"})

        return (
            fighter["fighter_id"],
            category["category_id"],
            tournament["tournament_id"],
        )

    def test_create_registration(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        reg = svc.create(
            {
                "fighter_id": fid,
                "category_id": cid,
                "tournament_id": tid,
                "weight_in_weight_kg": 68.5,
                "is_approved": False,
            }
        )
        assert reg["fighter_id"] == fid
        assert reg["is_approved"] is False

    def test_create_duplicate_raises(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )
        with pytest.raises(ValueError, match="already exists"):
            svc.create(
                {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
            )

    def test_create_missing_ids_raises(self, session_factory):
        svc = RegistrationService(session_factory)
        with pytest.raises(ValueError):
            svc.create({"fighter_id": 1})  # missing category_id, tournament_id

    def test_get_registration(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )

        found = svc.get(fid, cid, tid)
        assert found is not None
        assert found["fighter_id"] == fid

    def test_get_nonexistent_returns_none(self, session_factory):
        svc = RegistrationService(session_factory)
        assert svc.get(999, 999, 999) is None

    def test_list_all(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )
        results = svc.list_all()
        assert any(r["fighter_id"] == fid for r in results)

    def test_list_by_tournament(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )
        results = svc.list_by_tournament(tid)
        assert all(r["tournament_id"] == tid for r in results)

    def test_list_by_fighter(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )
        results = svc.list_by_fighter(fid)
        assert all(r["fighter_id"] == fid for r in results)

    def test_list_pending_approvals(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {
                "fighter_id": fid,
                "category_id": cid,
                "tournament_id": tid,
                "is_approved": False,
            }
        )
        pending = svc.list_pending_approvals(tid)
        assert all(not r["is_approved"] for r in pending)

    def test_update_registration(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )
        updated = svc.update(
            {
                "fighter_id": fid,
                "category_id": cid,
                "tournament_id": tid,
                "weight_in_weight_kg": 72.0,
                "is_approved": True,
            }
        )
        assert updated["weight_in_weight_kg"] == 72.0
        assert updated["is_approved"] is True

    def test_approve_registration(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )
        approved = svc.approve(fid, cid, tid)
        assert approved["is_approved"] is True

    def test_delete_registration(self, session_factory, setup_ids):
        fid, cid, tid = setup_ids
        svc = RegistrationService(session_factory)
        svc.create(
            {"fighter_id": fid, "category_id": cid, "tournament_id": tid}
        )
        svc.delete(fid, cid, tid)
        assert svc.get(fid, cid, tid) is None

    def test_delete_nonexistent_raises(self, session_factory):
        svc = RegistrationService(session_factory)
        with pytest.raises(ValueError, match="not found"):
            svc.delete(999, 999, 999)
