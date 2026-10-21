"""Tests for src/server/app.py (request handling and client loop).

Sockets and the router are mocked, so no network or database is used.
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from src.common.protocol import (
    ErrorCode,
    MalformedMessageError,
    MessageTooLargeError,
)
from src.server import app

ADDR = ("127.0.0.1", 50000)


@pytest.fixture
def router():
    mock = MagicMock()
    mock.handle.return_value = {"success": True, "data": [], "error": None}
    return mock


class TestHandleRequest:
    def test_valid_request_is_routed(self, router):
        request = {"resource": "fighters", "action": "list"}
        response = app.handle_request(request, router)
        router.handle.assert_called_once_with(request)
        assert response["success"] is True

    @pytest.mark.parametrize(
        "request_",
        [
            [1, 2],
            "text",
            None,
            {"action": "list"},
            {"resource": "fighters"},
            {"resource": ["x"], "action": "list"},
            {"resource": "fighters", "action": 5},
            {"resource": "nope", "action": "list"},
            {"resource": "fighters", "action": "list", "payload": [1]},
        ],
    )
    def test_invalid_requests_get_error_without_routing(
        self, router, request_
    ):
        response = app.handle_request(request_, router)
        assert response["success"] is False
        assert response["error_code"] == ErrorCode.BAD_REQUEST
        router.handle.assert_not_called()

    def test_router_crash_becomes_internal_error(self, router):
        router.handle.side_effect = RuntimeError("boom")
        response = app.handle_request(
            {"resource": "fighters", "action": "list"}, router
        )
        assert response["error_code"] == ErrorCode.INTERNAL_ERROR
        assert "boom" not in response["error"]


class TestServeClient:
    """serve_client with receive/send patched (mocked socket)."""

    def _run(self, router, incoming, send_side_effect=None):
        sock = MagicMock(spec=socket.socket)
        sent = []

        def fake_send(_sock, message):
            if send_side_effect:
                raise send_side_effect
            sent.append(message)

        with (
            patch.object(app, "receive_message", side_effect=incoming),
            patch.object(app, "send_message", side_effect=fake_send),
        ):
            app.serve_client(sock, ADDR, router, timeout=5)
        return sock, sent

    def test_answers_each_request_then_stops_on_disconnect(self, router):
        request = {"resource": "fighters", "action": "list"}
        sock, sent = self._run(
            router, [request, request, ConnectionError("bye")]
        )
        assert len(sent) == 2
        assert router.handle.call_count == 2
        sock.settimeout.assert_called_once_with(5)
        sock.__exit__.assert_called()  # socket closed via `with`

    def test_malformed_json_gets_error_and_connection_continues(self, router):
        request = {"resource": "fighters", "action": "list"}
        _, sent = self._run(
            router,
            [
                MalformedMessageError("Malformed JSON body"),
                request,
                ConnectionError(),
            ],
        )
        assert sent[0]["success"] is False
        assert "Malformed" in sent[0]["error"]
        assert sent[1]["success"] is True

    def test_oversized_message_gets_error_then_closes(self, router):
        _, sent = self._run(
            router, [MessageTooLargeError("too big"), {"never": "read"}]
        )
        assert len(sent) == 1
        assert sent[0]["success"] is False

    def test_timeout_closes_connection(self, router):
        _, sent = self._run(router, [socket.timeout()])
        assert sent == []

    def test_os_error_closes_connection(self, router):
        _, sent = self._run(router, [OSError("reset")])
        assert sent == []

    def test_send_failure_stops_serving(self, router):
        request = {"resource": "fighters", "action": "list"}
        _, sent = self._run(
            router, [request, request], send_side_effect=OSError("pipe")
        )
        assert sent == []
        assert router.handle.call_count == 1

    def test_invalid_request_does_not_stop_the_loop(self, router):
        good = {"resource": "fighters", "action": "list"}
        _, sent = self._run(
            router, [{"resource": ["x"]}, good, ConnectionError()]
        )
        assert [m["success"] for m in sent] == [False, True]


class TestRunServer:
    def test_serves_clients_sequentially_and_stops_on_ctrl_c(self):
        server_sock = MagicMock()
        server_sock.__enter__.return_value = server_sock
        client_a, client_b = MagicMock(), MagicMock()
        server_sock.accept.side_effect = [
            (client_a, ("1.1.1.1", 1)),
            (client_b, ("2.2.2.2", 2)),
            KeyboardInterrupt(),
        ]
        with (
            patch.object(app.socket, "socket", return_value=server_sock),
            patch.object(app, "Router"),
            patch.object(app, "serve_client") as serve,
        ):
            app.run_server("127.0.0.1", 9999, session_factory=MagicMock())

        server_sock.bind.assert_called_once_with(("127.0.0.1", 9999))
        server_sock.listen.assert_called_once_with(app.BACKLOG)
        assert app.BACKLOG == 1
        assert serve.call_count == 2
