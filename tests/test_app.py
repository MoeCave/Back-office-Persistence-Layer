"""Unit and concurrency tests for the asyncio TCP server."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import struct
import time
from typing import Any
from unittest.mock import MagicMock

from src.client.async_gateway import AsyncServerError, AsyncServerGateway
from src.common.protocol import (
    HEADER_FORMAT,
    MAX_MESSAGE_BYTES,
    ErrorCode,
    ok,
    read_message,
    write_message,
)
from src.server.app import handle_request, run_server


@asynccontextmanager
async def _running_server(
    router_handler: Any,
    **server_kwargs: Any,
) -> AsyncIterator[tuple[str, int, asyncio.Event]]:
    """Start ``run_server`` on an ephemeral port and stop it on exit."""
    stop_event = asyncio.Event()
    started = asyncio.Event()
    bound: dict[str, Any] = {}

    def _on_started(host: str, port: int) -> None:
        bound["host"] = host
        bound["port"] = port
        started.set()

    task = asyncio.create_task(
        run_server(
            host="127.0.0.1",
            port=0,
            session_factory=MagicMock(),
            stop_event=stop_event,
            on_started=_on_started,
            **server_kwargs,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5.0)
    # Patch Router.handle on the created router via monkeypatch-style hook
    # when custom behaviour is needed by callers.
    _ = router_handler
    try:
        yield bound["host"], bound["port"], stop_event
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=5.0)


def test_handle_request_rejects_invalid_envelope() -> None:
    """``handle_request`` returns ``BAD_REQUEST`` without calling router."""
    router = MagicMock()
    resp = handle_request({"resource": "unknown"}, router)
    assert resp["success"] is False
    assert resp["error_code"] == ErrorCode.BAD_REQUEST
    router.handle.assert_not_called()


def test_handle_request_catches_unexpected_router_exception() -> None:
    """Unexpected router exceptions map to ``INTERNAL_ERROR``."""
    router = MagicMock()
    router.handle.side_effect = RuntimeError("boom")
    resp = handle_request(
        {"resource": "fighters", "action": "list", "payload": {}},
        router,
    )
    assert resp["success"] is False
    assert resp["error_code"] == ErrorCode.INTERNAL_ERROR


async def test_concurrent_clients_do_not_block_each_other(
    monkeypatch: Any,
) -> None:
    """Multiple slow DB calls run concurrently across thread workers."""

    def _slow_handle(self: Any, request: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.15)
        return ok({"client": request["payload"].get("id")})

    monkeypatch.setattr("src.server.router.Router.handle", _slow_handle)

    async with _running_server(None, db_workers=6) as (host, port, _):

        async def _call(idx: int) -> Any:
            async with AsyncServerGateway(host, port) as gw:
                return await gw.request("fighters", "list", {"id": idx})

        start = time.perf_counter()
        results = await asyncio.gather(*(_call(i) for i in range(6)))
        elapsed = time.perf_counter() - start

    assert results == [{"client": i} for i in range(6)]
    # Sequential execution would take >= 0.90s; concurrent takes ~0.15-0.35s.
    assert elapsed < 0.60


async def test_malformed_json_returns_error_and_keeps_session_open(
    monkeypatch: Any,
) -> None:
    """Server replies ``BAD_REQUEST`` on bad JSON and serves next frame."""
    monkeypatch.setattr(
        "src.server.router.Router.handle",
        lambda self, req: ok({"echo": req["action"]}),
    )

    async with _running_server(None) as (host, port, _):
        reader, writer = await asyncio.open_connection(host, port)
        bad = b"{corrupt"
        writer.write(struct.pack(HEADER_FORMAT, len(bad)) + bad)
        await writer.drain()

        err_resp = await read_message(reader)
        assert err_resp["success"] is False
        assert err_resp["error_code"] == ErrorCode.BAD_REQUEST

        await write_message(
            writer,
            {"resource": "fighters", "action": "list", "payload": {}},
        )
        ok_resp = await read_message(reader)
        assert ok_resp == ok({"echo": "list"})

        writer.close()
        await writer.wait_closed()


async def test_oversized_frame_returns_error_and_closes_socket() -> None:
    """Declaring > ``MAX_MESSAGE_BYTES`` triggers error reply and EOF."""
    async with _running_server(None) as (host, port, _):
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(struct.pack(HEADER_FORMAT, MAX_MESSAGE_BYTES + 1))
        await writer.drain()

        err_resp = await read_message(reader)
        assert err_resp["success"] is False
        assert err_resp["error_code"] == ErrorCode.BAD_REQUEST
        assert await reader.read(1) == b""

        writer.close()
        await writer.wait_closed()


async def test_idle_client_disconnected_after_timeout() -> None:
    """Inactive connections are closed once ``client_timeout`` expires."""
    async with _running_server(None, client_timeout=0.15) as (host, port, _):
        reader, writer = await asyncio.open_connection(host, port)
        eof = await asyncio.wait_for(reader.read(1), timeout=2.0)
        assert eof == b""
        writer.close()
        await writer.wait_closed()


async def test_max_connections_rejects_excess_clients() -> None:
    """Connections beyond ``max_connections`` receive immediate EOF."""
    async with _running_server(None, max_connections=2) as (host, port, _):
        r1, w1 = await asyncio.open_connection(host, port)
        r2, w2 = await asyncio.open_connection(host, port)
        await asyncio.sleep(0.05)

        r3, w3 = await asyncio.open_connection(host, port)
        eof = await asyncio.wait_for(r3.read(1), timeout=2.0)
        assert eof == b""

        for writer in (w1, w2, w3):
            writer.close()
            await writer.wait_closed()


async def test_graceful_shutdown_cancels_active_clients() -> None:
    """Setting ``stop_event`` disconnects active idle clients cleanly."""
    async with _running_server(None, client_timeout=60.0) as (
        host,
        port,
        stop_event,
    ):
        reader, writer = await asyncio.open_connection(host, port)
        await asyncio.sleep(0.05)
        stop_event.set()
        eof = await asyncio.wait_for(reader.read(1), timeout=2.0)
        assert eof == b""
        writer.close()
        await writer.wait_closed()


async def test_async_gateway_raises_typed_error_on_failure(
    monkeypatch: Any,
) -> None:
    """``AsyncServerGateway`` raises ``AsyncServerError`` with error code."""
    monkeypatch.setattr(
        "src.server.router.Router.handle",
        lambda self, req: {
            "success": False,
            "data": None,
            "error": "Fighter 99 not found.",
            "error_code": ErrorCode.NOT_FOUND,
        },
    )

    async with _running_server(None) as (host, port, _):
        async with AsyncServerGateway(host, port) as gw:
            try:
                await gw.resource("fighters").call("get", {"id": 99})
            except AsyncServerError as exc:
                assert exc.code == ErrorCode.NOT_FOUND
                assert "99" in exc.message
            else:
                raise AssertionError("Expected AsyncServerError")
