"""TCP server: concurrent clients over asyncio streams.

The server accepts multiple concurrent TCP connections via
``asyncio.start_server``, dispatches each client's framed JSON requests
through :class:`~src.server.router.Router`, and replies asynchronously.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.common.protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ErrorCode,
    MalformedMessageError,
    MessageTooLargeError,
    error,
    read_message,
    validate_request,
    write_message,
)
from src.server.router import Router

log = logging.getLogger(__name__)

DEFAULT_BACKLOG = 128
DEFAULT_CLIENT_TIMEOUT = 900.0

__all__ = [
    "DEFAULT_BACKLOG",
    "DEFAULT_CLIENT_TIMEOUT",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "handle_client",
    "handle_request",
    "run_server",
]


async def run_server(
    host: str,
    port: int,
    session_factory: Any,
    backlog: int = DEFAULT_BACKLOG,
) -> None:
    """Start the asyncio TCP server and serve until cancelled."""
    router = Router(session_factory)
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, router),
        host=host,
        port=port,
        backlog=backlog,
    )
    async with server:
        log.info(
            "Listening on %s:%d (concurrent asyncio mode).",
            host,
            port,
        )
        await server.serve_forever()


def handle_request(request: Any, router: Router) -> dict[str, Any]:
    """Validate *request* and return the response for it. Never raises."""
    validation_error = validate_request(request)
    if validation_error:
        return error(validation_error, ErrorCode.BAD_REQUEST)
    try:
        return router.handle(request)
    except Exception:  # noqa: BLE001 - last line of defence
        log.exception("Router failed unexpectedly")
        return error("Internal server error.", ErrorCode.INTERNAL_ERROR)


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    router: Router,
) -> None:
    """Serve one connected client over asyncio streams."""
    peer = writer.get_extra_info("peername")
    log.info("Client connected: %s", peer)
    try:
        while True:
            try:
                request = await read_message(reader)
            except MalformedMessageError as exc:
                if not await _try_write(writer, error(str(exc)), peer):
                    break
                continue
            except MessageTooLargeError as exc:
                await _try_write(writer, error(str(exc)), peer)
                break
            except ConnectionError:
                break

            log.debug("Request from %s: %s", peer, request)
            # Note: router.handle is still synchronous; offloaded in Step 4.
            response = handle_request(request, router)
            if not await _try_write(writer, response, peer):
                break
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
        log.info("Client disconnected: %s", peer)


async def _try_write(
    writer: asyncio.StreamWriter,
    response: dict[str, Any],
    peer: Any,
) -> bool:
    """Write *response* to *writer*; return False if stream is closed."""
    try:
        await write_message(writer, response)
    except OSError as exc:
        log.warning("Failed to send response to %s: %s", peer, exc)
        return False
    return True
