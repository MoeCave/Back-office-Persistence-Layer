"""Router error-to-response mapping (service layer mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.common.protocol import ErrorCode
from src.server.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from src.server.router import Router


@pytest.fixture
def router():
    router = Router(MagicMock())
    router._fighters = MagicMock()
    return router, router._fighters


def _call(router, action="list", payload=None):
    return router.handle(
        {"resource": "fighters", "action": action, "payload": payload or {}}
    )


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (NotFoundError("x"), ErrorCode.NOT_FOUND),
        (ValidationError("x"), ErrorCode.VALIDATION_ERROR),
        (ConflictError("x"), ErrorCode.CONFLICT),
        (ValueError("x"), ErrorCode.BAD_REQUEST),
    ],
)
def test_known_errors_map_to_codes(router, exception, code):
    router, service = router
    service.list_all.side_effect = exception
    response = _call(router)
    assert response["success"] is False
    assert response["error_code"] == code
    assert response["error"] == "x"


def test_integrity_error_hides_sql(router):
    router, service = router
    service.list_all.side_effect = IntegrityError(
        "INSERT INTO secret_table", {}, Exception("FOREIGN KEY failed")
    )
    response = _call(router)
    assert response["error_code"] == ErrorCode.CONFLICT
    assert "secret_table" not in response["error"]


def test_unexpected_error_is_generic(router):
    router, service = router
    service.list_all.side_effect = RuntimeError("db password is hunter2")
    response = _call(router)
    assert response["error_code"] == ErrorCode.INTERNAL_ERROR
    assert "hunter2" not in response["error"]


def test_unknown_action_code(router):
    router, _ = router
    assert _call(router, "fly")["error_code"] == ErrorCode.UNKNOWN_ACTION


def test_not_found_for_missing_entity(router):
    router, service = router
    service.get_by_id.return_value = None
    response = _call(router, "get", {"fighter_id": 5})
    assert response["error_code"] == ErrorCode.NOT_FOUND
    assert "id=5" in response["error"]


def test_non_integer_id_is_validation_error(router):
    router, _ = router
    response = _call(router, "get", {"fighter_id": "abc"})
    assert response["error_code"] == ErrorCode.VALIDATION_ERROR


def test_pagination_is_validated_before_calling_service(router):
    router, service = router
    response = _call(router, "list_paginated", {"page": 0})
    assert response["error_code"] == ErrorCode.VALIDATION_ERROR
    service.list_paginated.assert_not_called()


def test_null_payload_is_treated_as_empty(router):
    router, service = router
    service.list_all.return_value = []
    response = router.handle(
        {"resource": "fighters", "action": "list", "payload": None}
    )
    assert response["success"] is True
