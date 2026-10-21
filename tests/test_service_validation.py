"""Regression tests for input validation in the service layer."""

from __future__ import annotations

import pytest

from src.server.errors import ConflictError, NotFoundError, ValidationError
from src.server.services import (
    CategoryService,
    FighterService,
    MatchService,
    RegistrationService,
    TournamentService,
)


@pytest.fixture
def fighters(session_factory):
    return FighterService(session_factory)


@pytest.fixture
def tournaments(session_factory):
    return TournamentService(session_factory)


class TestFighterValidation:
    def test_null_names_are_rejected_not_crashing(self, fighters):
        with pytest.raises(ValidationError, match="first_name"):
            fighters.create({"first_name": None, "last_name": "X"})

    def test_invalid_birth_date_is_rejected(self, fighters):
        with pytest.raises(ValidationError, match="birth_date"):
            fighters.create(
                {
                    "first_name": "A",
                    "last_name": "B",
                    "birth_date": "31/12/2000",
                }
            )

    def test_update_changes_birth_date(self, fighters):
        created = fighters.create({"first_name": "A", "last_name": "B"})
        updated = fighters.update(
            created["fighter_id"], {"birth_date": "2000-05-05"}
        )
        assert updated["birth_date"].startswith("2000-05-05")

    def test_duplicate_email_on_create_conflicts(self, fighters):
        fighters.create(
            {"first_name": "A", "last_name": "B", "email": "dup@x.com"}
        )
        with pytest.raises(ConflictError, match="already exists"):
            fighters.create(
                {"first_name": "C", "last_name": "D", "email": "dup@x.com"}
            )

    def test_duplicate_email_on_update_conflicts(self, fighters):
        fighters.create(
            {"first_name": "A", "last_name": "B", "email": "one@x.com"}
        )
        other = fighters.create({"first_name": "C", "last_name": "D"})
        with pytest.raises(ConflictError):
            fighters.update(other["fighter_id"], {"email": "one@x.com"})

    def test_keeping_own_email_on_update_is_allowed(self, fighters):
        created = fighters.create(
            {"first_name": "A", "last_name": "B", "email": "me@x.com"}
        )
        updated = fighters.update(
            created["fighter_id"], {"email": "me@x.com", "country": "ES"}
        )
        assert updated["country"] == "ES"

    def test_missing_fighter_raises_not_found_error(self, fighters):
        with pytest.raises(NotFoundError):
            fighters.delete(999_999)

    def test_approve_missing_registration_is_not_found(self, fighters):
        with pytest.raises(NotFoundError):
            fighters.approve_registration(998, 998, 998)


class TestTournamentValidation:
    def test_invalid_date_is_rejected(self, tournaments):
        with pytest.raises(ValidationError, match="start_date"):
            tournaments.create({"name": "T", "start_date": "tomorrow"})

    def test_end_before_start_is_rejected(self, tournaments):
        with pytest.raises(ValidationError, match="end_date"):
            tournaments.create(
                {
                    "name": "T",
                    "start_date": "2026-05-02",
                    "end_date": "2026-05-01",
                }
            )

    def test_update_changes_dates(self, tournaments):
        created = tournaments.create({"name": "T", "start_date": "2026-05-01"})
        updated = tournaments.update(
            created["tournament_id"], {"end_date": "2026-05-03"}
        )
        assert updated["end_date"].startswith("2026-05-03")

    def test_update_rejects_inconsistent_dates(self, tournaments):
        created = tournaments.create({"name": "T", "start_date": "2026-05-10"})
        with pytest.raises(ValidationError):
            tournaments.update(
                created["tournament_id"], {"end_date": "2026-05-01"}
            )

    def test_tatami_for_missing_tournament_is_not_found(self, tournaments):
        with pytest.raises(NotFoundError):
            tournaments.add_tatami(999_999, {"name": "Mat 1"})

    def test_tatami_area_must_be_numeric(self, tournaments):
        created = tournaments.create({"name": "T"})
        with pytest.raises(ValidationError, match="area_size"):
            tournaments.add_tatami(
                created["tournament_id"],
                {"name": "Mat", "area_size": "big"},
            )


class TestOtherServices:
    def test_category_weight_must_be_numeric(self, session_factory):
        with pytest.raises(ValidationError, match="weight_min_kg"):
            CategoryService(session_factory).create(
                {"name": "C", "weight_min_kg": "abc"}
            )

    def test_match_requires_integer_ids(self, session_factory):
        with pytest.raises(ValidationError, match="tournament_id"):
            MatchService(session_factory).create({"tournament_id": "x"})

    def test_match_invalid_scheduled_time(self, session_factory):
        with pytest.raises(ValidationError, match="scheduled_time"):
            MatchService(session_factory).create(
                {"tournament_id": 1, "scheduled_time": "noon"}
            )

    def test_registration_requires_all_ids(self, session_factory):
        with pytest.raises(ValidationError, match="category_id"):
            RegistrationService(session_factory).create({"fighter_id": 1})

    def test_registration_weight_must_be_numeric(self, session_factory):
        with pytest.raises(ValidationError, match="weight_in_weight_kg"):
            RegistrationService(session_factory).create(
                {
                    "fighter_id": 1,
                    "category_id": 1,
                    "tournament_id": 1,
                    "weight_in_weight_kg": "heavy",
                }
            )
