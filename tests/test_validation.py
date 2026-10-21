"""Unit tests for src/server/validation.py."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.server.errors import ValidationError
from src.server.validation import (
    clean_str,
    optional_int,
    optional_number,
    pagination,
    parse_datetime,
    require_int,
)


class TestCleanStr:
    def test_strips_whitespace(self):
        assert clean_str("  Ana ") == "Ana"

    @pytest.mark.parametrize("value", [None, 5, [], {}])
    def test_non_string_becomes_empty(self, value):
        assert clean_str(value) == ""


class TestRequireInt:
    def test_valid_int_and_numeric_string(self):
        assert require_int({"id": 3}, "id") == 3
        assert require_int({"id": "7"}, "id") == 7

    def test_missing_key(self):
        with pytest.raises(ValidationError, match="Missing required"):
            require_int({}, "id")

    @pytest.mark.parametrize(
        "value", ["abc", [], {}, True, 1.5, float("inf"), float("nan")]
    )
    def test_invalid_values(self, value):
        with pytest.raises(ValidationError, match="must be an integer"):
            require_int({"id": value}, "id")


class TestOptionalHelpers:
    def test_optional_int_none_when_absent(self):
        assert optional_int({}, "x") is None
        assert optional_int({"x": None}, "x") is None

    def test_optional_int_converts(self):
        assert optional_int({"x": "4"}, "x") == 4

    def test_optional_number_accepts_int_float_and_string(self):
        assert optional_number({"w": 70}, "w") == 70.0
        assert optional_number({"w": "68.5"}, "w") == 68.5

    @pytest.mark.parametrize(
        "value", ["abc", True, [], {}, float("inf"), float("nan")]
    )
    def test_optional_number_rejects_invalid(self, value):
        with pytest.raises(ValidationError, match="must be a"):
            optional_number({"w": value}, "w")


class TestPagination:
    def test_defaults(self):
        assert pagination({}) == (1, 10)

    def test_valid_values(self):
        assert pagination({"page": 2, "page_size": 5}) == (2, 5)

    @pytest.mark.parametrize(
        "payload",
        [
            {"page": 0},
            {"page": -5},
            {"page_size": 0},
            {"page_size": 101},
            {"page_size": "x"},
        ],
    )
    def test_invalid_values(self, payload):
        with pytest.raises(ValidationError):
            pagination(payload)


class TestParseDatetime:
    def test_none_and_empty(self):
        assert parse_datetime(None, "d") is None
        assert parse_datetime("", "d") is None

    def test_date_only(self):
        assert parse_datetime("2026-03-01", "d") == datetime(2026, 3, 1)

    def test_date_and_time(self):
        assert parse_datetime("2026-03-01 14:30", "d") == datetime(
            2026, 3, 1, 14, 30
        )

    def test_iso_round_trip(self):
        assert parse_datetime("2026-03-01T14:30:00", "d") == datetime(
            2026, 3, 1, 14, 30
        )

    @pytest.mark.parametrize("value", ["31/12/2000", "garbage", 5, []])
    def test_invalid_raises(self, value):
        with pytest.raises(ValidationError, match="'d'"):
            parse_datetime(value, "d")
