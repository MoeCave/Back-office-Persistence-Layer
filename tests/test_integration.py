"""End-to-end tests: real TCP sockets, real router, in-memory SQLite.

A background asyncio server thread serves clients with ``run_server``
while the test talks to it through ``ServerGateway`` or raw frames.
"""

from __future__ import annotations

import asyncio
import json
import socket
import struct
import threading

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.client.gateway import ServerError, ServerGateway
from src.common.protocol import (
    HEADER_FORMAT,
    ErrorCode,
    receive_message,
    send_message,
)
from src.domain.db import Base
import src.domain.models  # noqa: F401 - registers the tables
from src.server.app import run_server


@pytest.fixture
def live_server():
    """Start an asyncio server thread; yield its ephemeral port."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)

    ready = threading.Event()
    bound: dict[str, int] = {}
    holder: dict[str, asyncio.AbstractEventLoop | asyncio.Event] = {}

    def _thread_main() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        holder["loop"] = loop
        holder["stop"] = stop_event

        def _on_started(_host: str, port: int) -> None:
            bound["port"] = port
            ready.set()

        try:
            loop.run_until_complete(
                run_server(
                    host="127.0.0.1",
                    port=0,
                    session_factory=session_factory,
                    client_timeout=5.0,
                    stop_event=stop_event,
                    on_started=_on_started,
                )
            )
        finally:
            loop.close()

    thread = threading.Thread(target=_thread_main, daemon=True)
    thread.start()
    assert ready.wait(timeout=5.0), "Async server failed to start"
    try:
        yield bound["port"]
    finally:
        loop = holder.get("loop")
        stop = holder.get("stop")
        if isinstance(loop, asyncio.AbstractEventLoop) and isinstance(
            stop, asyncio.Event
        ):
            loop.call_soon_threadsafe(stop.set)
        thread.join(timeout=5.0)
        engine.dispose()


def _raw_frame(sock, body: bytes):
    sock.sendall(struct.pack(HEADER_FORMAT, len(body)) + body)


class TestGatewayEndToEnd:
    def test_full_crud_cycle(self, live_server):
        with ServerGateway(port=live_server) as gw:
            created = gw.fighters.create(
                first_name="Ana", last_name="Lopez", birth_date="1999-01-02"
            )
            fighter_id = created["fighter_id"]
            assert gw.fighters.get(fighter_id)["first_name"] == "Ana"

            updated = gw.fighters.update(
                fighter_id, first_name="Anna", birth_date="2000-05-05"
            )
            assert updated["first_name"] == "Anna"
            assert updated["birth_date"].startswith("2000-05-05")
            assert len(gw.fighters.list_all()) == 1

            gw.fighters.delete(fighter_id)
            assert gw.fighters.get(fighter_id) is None
            assert gw.fighters.list_all() == []

    def test_registration_workflow(self, live_server):
        with ServerGateway(port=live_server) as gw:
            fighter = gw.fighters.create(first_name="A", last_name="B")
            tournament = gw.tournaments.create(name="Open")
            category = gw.categories.create(
                name="C", weight_min_kg=50, weight_max_kg=60
            )
            key = {
                "fighter_id": fighter["fighter_id"],
                "category_id": category["category_id"],
                "tournament_id": tournament["tournament_id"],
            }
            created = gw.registrations.add({**key, "weight_in_weight_kg": 55})
            assert created["is_approved"] is False
            approved = gw.fighters.approve_registration(*key.values())
            assert approved["is_approved"] is True
            with pytest.raises(ServerError) as info:
                gw.registrations.add(key)
            assert info.value.code == ErrorCode.CONFLICT

    def test_server_error_codes_reach_the_client(self, live_server):
        with ServerGateway(port=live_server) as gw:
            with pytest.raises(ServerError) as info:
                gw.fighters.create(first_name="", last_name="")
            assert info.value.code == ErrorCode.VALIDATION_ERROR
            with pytest.raises(ServerError) as info:
                gw.request("fighters", "explode")
            assert info.value.code == ErrorCode.UNKNOWN_ACTION


class TestServerRobustness:
    """Bad input must never kill the server or leak internals."""

    @pytest.mark.parametrize(
        "request_",
        [
            {"resource": ["x"], "action": "list"},
            {"resource": "fighters", "action": 5},
            {"resource": "fighters", "action": "list", "payload": "abc"},
            {
                "resource": "fighters",
                "action": "create",
                "payload": {"first_name": None, "last_name": "X"},
            },
            {
                "resource": "fighters",
                "action": "list_paginated",
                "payload": {"page": -5, "page_size": "x"},
            },
            {
                "resource": "matches",
                "action": "create",
                "payload": {"tournament_id": 999},
            },
            {
                "resource": "registrations",
                "action": "create",
                "payload": {
                    "fighter_id": 9,
                    "category_id": 9,
                    "tournament_id": 9,
                },
            },
            {
                "resource": "categories",
                "action": "create",
                "payload": {"name": "C", "weight_min_kg": "abc"},
            },
        ],
    )
    def test_bad_requests_get_clean_errors_and_server_survives(
        self, live_server, request_
    ):
        with socket.create_connection(("127.0.0.1", live_server)) as sock:
            send_message(sock, request_)
            response = receive_message(sock)
            assert response["success"] is False
            assert response["error_code"] in {
                ErrorCode.BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                ErrorCode.CONFLICT,
            }
            assert "SQL" not in response["error"]
            # same connection still works
            send_message(sock, {"resource": "fighters", "action": "list"})
            assert receive_message(sock)["success"] is True

    def test_invalid_json_gets_error_and_connection_stays_open(
        self, live_server
    ):
        with socket.create_connection(("127.0.0.1", live_server)) as sock:
            _raw_frame(sock, b"{not json")
            response = receive_message(sock)
            assert response["success"] is False
            assert "Malformed" in response["error"]
            send_message(sock, {"resource": "fighters", "action": "list"})
            assert receive_message(sock)["success"] is True

    def test_invalid_utf8_is_handled(self, live_server):
        with socket.create_connection(("127.0.0.1", live_server)) as sock:
            _raw_frame(sock, b"\xff\xfe\xfa")
            assert receive_message(sock)["success"] is False

    def test_server_accepts_next_client_after_disconnect(self, live_server):
        for _ in range(2):
            with ServerGateway(port=live_server) as gw:
                assert gw.fighters.list_all() == []

    def test_unexpected_payload_type_in_json_value(self, live_server):
        with socket.create_connection(("127.0.0.1", live_server)) as sock:
            _raw_frame(sock, json.dumps([1, 2, 3]).encode())
            assert receive_message(sock)["success"] is False
