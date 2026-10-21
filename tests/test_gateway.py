"""Tests for src/client/gateway.py with a mocked socket."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.client import gateway as gw_module
from src.client.gateway import (
    ConnectionFailedError,
    ServerError,
    ServerGateway,
)
from src.common.protocol import ErrorCode, error, ok


@pytest.fixture
def gateway():
    """A connected gateway whose socket and framing are mocked."""
    with patch.object(gw_module.socket, "socket") as sock_cls:
        sock_cls.return_value = MagicMock()
        gw = ServerGateway()
        gw.connect()
        yield gw
        gw.close()


def _reply(response):
    return patch.object(gw_module, "receive_message", return_value=response)


class TestConnection:
    def test_connect_failure_raises_connection_failed(self):
        with patch.object(gw_module.socket, "socket") as sock_cls:
            sock_cls.return_value.connect.side_effect = OSError("refused")
            with pytest.raises(ConnectionFailedError, match="Is the server"):
                ServerGateway(port=1).connect()

    def test_request_before_connect_fails(self):
        with pytest.raises(ConnectionFailedError, match="Not connected"):
            ServerGateway().request("fighters", "list")

    def test_context_manager_closes_socket(self):
        with patch.object(gw_module.socket, "socket") as sock_cls:
            sock = sock_cls.return_value
            with ServerGateway():
                pass
            sock.close.assert_called_once()


class TestRequest:
    def test_sends_envelope_and_returns_data(self, gateway):
        with (
            patch.object(gw_module, "send_message") as send,
            _reply(ok([1, 2])),
        ):
            data = gateway.request("fighters", "list")
        assert data == [1, 2]
        envelope = send.call_args.args[1]
        assert envelope == {
            "resource": "fighters",
            "action": "list",
            "payload": {},
        }

    def test_error_response_raises_server_error_with_code(self, gateway):
        with (
            patch.object(gw_module, "send_message"),
            _reply(error("nope", ErrorCode.VALIDATION_ERROR)),
        ):
            with pytest.raises(ServerError, match="nope") as info:
                gateway.request("fighters", "create", {})
        assert info.value.code == ErrorCode.VALIDATION_ERROR

    def test_error_without_code_defaults_to_bad_request(self, gateway):
        with (
            patch.object(gw_module, "send_message"),
            _reply({"success": False, "error": "legacy"}),
        ):
            with pytest.raises(ServerError) as info:
                gateway.request("fighters", "list")
        assert info.value.code == ErrorCode.BAD_REQUEST

    def test_dropped_connection_propagates(self, gateway):
        with (
            patch.object(gw_module, "send_message"),
            patch.object(
                gw_module, "receive_message", side_effect=ConnectionError("x")
            ),
        ):
            with pytest.raises(ConnectionError):
                gateway.request("fighters", "list")


class TestGetOrNone:
    def test_not_found_becomes_none(self, gateway):
        with (
            patch.object(gw_module, "send_message"),
            _reply(error("missing", ErrorCode.NOT_FOUND)),
        ):
            assert gateway.fighters.get(99) is None

    def test_other_errors_are_not_swallowed(self, gateway):
        with (
            patch.object(gw_module, "send_message"),
            _reply(error("Internal server error.", ErrorCode.INTERNAL_ERROR)),
        ):
            with pytest.raises(ServerError):
                gateway.fighters.get(1)

    def test_success_returns_data(self, gateway):
        with (
            patch.object(gw_module, "send_message"),
            _reply(ok({"fighter_id": 1})),
        ):
            assert gateway.fighters.get(1) == {"fighter_id": 1}


class TestProxies:
    """Each proxy method must send the documented resource/action."""

    @pytest.mark.parametrize(
        ("call", "resource", "action", "payload"),
        [
            (lambda g: g.fighters.list_all(), "fighters", "list", {}),
            (
                lambda g: g.fighters.create(first_name="A", last_name="B"),
                "fighters",
                "create",
                {"first_name": "A", "last_name": "B"},
            ),
            (
                lambda g: g.fighters.update(3, country="ES"),
                "fighters",
                "update",
                {"fighter_id": 3, "country": "ES"},
            ),
            (
                lambda g: g.fighters.delete(3),
                "fighters",
                "delete",
                {"fighter_id": 3},
            ),
            (
                lambda g: g.tournaments.list_tatamis(2),
                "tournaments",
                "list_tatamis",
                {"tournament_id": 2},
            ),
            (
                lambda g: g.categories.get_by_weight_range(50, 60),
                "categories",
                "search_by_weight_range",
                {"min_kg": 50, "max_kg": 60},
            ),
            (
                lambda g: g.matches.get_by_round(1, 2),
                "matches",
                "get_by_round",
                {"tournament_id": 1, "round_number": 2},
            ),
            (
                lambda g: g.registrations.add({"fighter_id": 1}),
                "registrations",
                "create",
                {"fighter_id": 1},
            ),
        ],
    )
    def test_proxy_sends_expected_request(
        self, gateway, call, resource, action, payload
    ):
        with patch.object(gw_module, "send_message") as send, _reply(ok(None)):
            call(gateway)
        envelope = send.call_args.args[1]
        assert envelope["resource"] == resource
        assert envelope["action"] == action
        assert envelope["payload"] == payload
