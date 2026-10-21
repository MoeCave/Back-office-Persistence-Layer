"""
test_dto.py — unit tests for src/server/dto.py.

Covers to_dict() serialisation and from_dict() deserialisation for every DTO.
"""

from __future__ import annotations


from src.server.dto import (
    CategoryDTO,
    FighterDTO,
    MatchDTO,
    MedicalRecordDTO,
    RegistrationDTO,
    TatamiDTO,
    TournamentDTO,
)

# ── FighterDTO ───────────────────────────────────────────────────────────────


class TestFighterDTO:
    def test_to_dict_round_trip(self):
        dto = FighterDTO(
            fighter_id=1,
            first_name="Ana",
            last_name="García",
            gender="F",
            belt_level="blue",
            club_name="Club BCN",
            country="Spain",
            email="ana@example.com",
            phone=None,
            birth_date="1995-03-15",
            created_at="2026-01-01T00:00:00",
        )
        d = dto.to_dict()
        assert d["fighter_id"] == 1
        assert d["first_name"] == "Ana"
        assert d["last_name"] == "García"
        assert d["gender"] == "F"
        assert d["belt_level"] == "blue"
        assert d["phone"] is None

    def test_from_dict(self):
        d = {
            "fighter_id": 2,
            "first_name": "Carlos",
            "last_name": "López",
            "gender": "M",
            "belt_level": "black",
        }
        dto = FighterDTO.from_dict(d)
        assert dto.fighter_id == 2
        assert dto.first_name == "Carlos"
        assert dto.belt_level == "black"
        assert dto.phone is None  # optional field defaults to None

    def test_from_dict_missing_optional_fields(self):
        d = {"first_name": "Test", "last_name": "User"}
        dto = FighterDTO.from_dict(d)
        assert dto.fighter_id is None
        assert dto.gender is None

    def test_symmetry(self):
        """from_dict(to_dict(dto)) must reconstruct the same values."""
        original = FighterDTO(
            fighter_id=5,
            first_name="Yuki",
            last_name="Tanaka",
            gender=None,
            belt_level="purple",
            club_name=None,
            country="Japan",
            email=None,
            phone=None,
            birth_date=None,
            created_at=None,
        )
        reconstructed = FighterDTO.from_dict(original.to_dict())
        assert reconstructed.fighter_id == original.fighter_id
        assert reconstructed.last_name == original.last_name
        assert reconstructed.country == original.country


# ── MedicalRecordDTO ─────────────────────────────────────────────────────────


class TestMedicalRecordDTO:
    def test_to_dict(self):
        dto = MedicalRecordDTO(
            medical_record_id=1,
            fighter_id=1,
            blood_type="A+",
            notes="No conditions",
            conditions=None,
            doctor_name="Dr. Martínez",
        )
        d = dto.to_dict()
        assert d["blood_type"] == "A+"
        assert d["conditions"] is None

    def test_from_dict(self):
        d = {"medical_record_id": 1, "fighter_id": 3, "blood_type": "O-"}
        dto = MedicalRecordDTO.from_dict(d)
        assert dto.blood_type == "O-"
        assert dto.fighter_id == 3

    def test_symmetry(self):
        original = MedicalRecordDTO(
            medical_record_id=10,
            fighter_id=2,
            blood_type="B+",
            notes="Test",
            conditions=None,
            doctor_name=None,
        )
        assert (
            MedicalRecordDTO.from_dict(original.to_dict()).blood_type == "B+"
        )


# ── TournamentDTO ────────────────────────────────────────────────────────────


class TestTournamentDTO:
    def test_to_dict(self):
        dto = TournamentDTO(
            tournament_id=1,
            name="Copa Primavera",
            location="Barcelona",
            start_date="2026-06-01",
            end_date="2026-06-02",
            max_fighters=64,
            created_at="2026-01-01T00:00:00",
        )
        d = dto.to_dict()
        assert d["name"] == "Copa Primavera"
        assert d["max_fighters"] == 64

    def test_from_dict(self):
        d = {"tournament_id": 5, "name": "Grand Prix", "location": "Madrid"}
        dto = TournamentDTO.from_dict(d)
        assert dto.tournament_id == 5
        assert dto.location == "Madrid"

    def test_symmetry(self):
        original = TournamentDTO(
            tournament_id=7,
            name="Test Cup",
            location=None,
            start_date=None,
            end_date=None,
            max_fighters=None,
            created_at=None,
        )
        reconstructed = TournamentDTO.from_dict(original.to_dict())
        assert reconstructed.name == "Test Cup"
        assert reconstructed.location is None


# ── TatamiDTO ────────────────────────────────────────────────────────────────


class TestTatamiDTO:
    def test_to_dict(self):
        dto = TatamiDTO(
            tatami_id=1,
            tournament_id=1,
            name="Tatami A",
            mat_number=1,
            area_size=64.0,
            is_active=True,
        )
        d = dto.to_dict()
        assert d["name"] == "Tatami A"
        assert d["is_active"] is True

    def test_from_dict(self):
        d = {
            "tatami_id": 2,
            "tournament_id": 1,
            "name": "Tatami B",
            "mat_number": 2,
            "area_size": 36.0,
            "is_active": False,
        }
        dto = TatamiDTO.from_dict(d)
        assert dto.is_active is False
        assert dto.area_size == 36.0


# ── CategoryDTO ──────────────────────────────────────────────────────────────


class TestCategoryDTO:
    def test_to_dict(self):
        dto = CategoryDTO(
            category_id=1,
            name="Blue -70kg F",
            belt_level="blue",
            weight_min_kg=57.0,
            weight_max_kg=70.0,
            gender="F",
        )
        d = dto.to_dict()
        assert d["belt_level"] == "blue"
        assert d["gender"] == "F"

    def test_from_dict(self):
        d = {"category_id": 3, "name": "Test Cat", "belt_level": "black"}
        dto = CategoryDTO.from_dict(d)
        assert dto.category_id == 3
        assert dto.weight_min_kg is None  # optional

    def test_symmetry(self):
        original = CategoryDTO(
            category_id=4,
            name="X Cat",
            belt_level=None,
            weight_min_kg=None,
            weight_max_kg=None,
            gender=None,
        )
        reconstructed = CategoryDTO.from_dict(original.to_dict())
        assert reconstructed.name == "X Cat"


# ── MatchDTO ─────────────────────────────────────────────────────────────────


class TestMatchDTO:
    def test_to_dict(self):
        dto = MatchDTO(
            match_id=1,
            tournament_id=1,
            category_id=1,
            blue_fighter_id=1,
            red_fighter_id=2,
            winner_id=1,
            round_number=1,
            duration_seconds=185.0,
            win_method="ippon",
            scheduled_time="2026-06-01T09:00:00",
        )
        d = dto.to_dict()
        assert d["win_method"] == "ippon"
        assert d["duration_seconds"] == 185.0

    def test_from_dict(self):
        d = {"match_id": 10, "tournament_id": 1, "round_number": 2}
        dto = MatchDTO.from_dict(d)
        assert dto.match_id == 10
        assert dto.winner_id is None

    def test_symmetry(self):
        original = MatchDTO(
            match_id=None,
            tournament_id=2,
            category_id=None,
            blue_fighter_id=None,
            red_fighter_id=None,
            winner_id=None,
            round_number=None,
            duration_seconds=None,
            win_method=None,
            scheduled_time=None,
        )
        reconstructed = MatchDTO.from_dict(original.to_dict())
        assert reconstructed.tournament_id == 2
        assert reconstructed.win_method is None


# ── RegistrationDTO ──────────────────────────────────────────────────────────


class TestRegistrationDTO:
    def test_to_dict(self):
        dto = RegistrationDTO(
            fighter_id=1,
            category_id=1,
            tournament_id=1,
            weight_in_weight_kg=68.5,
            registration_date="2026-01-10T00:00:00",
            is_approved=False,
            last_update=None,
        )
        d = dto.to_dict()
        assert d["is_approved"] is False
        assert d["weight_in_weight_kg"] == 68.5

    def test_from_dict(self):
        d = {
            "fighter_id": 2,
            "category_id": 3,
            "tournament_id": 4,
            "is_approved": True,
        }
        dto = RegistrationDTO.from_dict(d)
        assert dto.fighter_id == 2
        assert dto.is_approved is True
        assert dto.weight_in_weight_kg is None

    def test_symmetry(self):
        original = RegistrationDTO(
            fighter_id=5,
            category_id=5,
            tournament_id=5,
            weight_in_weight_kg=75.0,
            registration_date="2026-02-01T00:00:00",
            is_approved=True,
            last_update=None,
        )
        reconstructed = RegistrationDTO.from_dict(original.to_dict())
        assert reconstructed.weight_in_weight_kg == 75.0
        assert reconstructed.is_approved is True
