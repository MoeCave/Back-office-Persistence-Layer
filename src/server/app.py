"""TCP server: one blocking client at a time.

The server accepts a client, answers its framed JSON requests through
the :class:`~src.server.router.Router` until it disconnects, and then
waits for the next client.
"""

from __future__ import annotations

import logging
import socket
from typing import Any

from src.common.protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ErrorCode,
    MalformedMessageError,
    MessageTooLargeError,
    error,
    receive_message,
    send_message,
    validate_request,
)
from src.server.router import Router

log = logging.getLogger(__name__)

BACKLOG = 1  # only one client at a time
DEFAULT_CLIENT_TIMEOUT = 900.0  # seconds of silence before dropping a client

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "handle_request",
    "run_server",
    "serve_client",
]


def run_server(
    host: str,
    port: int,
    session_factory,
    client_timeout: float | None = DEFAULT_CLIENT_TIMEOUT,
) -> None:
    """Start the blocking TCP server; stop with Ctrl+C."""
    router = Router(session_factory)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((host, port))
        server_sock.listen(BACKLOG)
        log.info("Listening on %s:%d (one client at a time).", host, port)
        try:
            while True:
                log.info("Waiting for a client connection...")
                client_sock, addr = server_sock.accept()
                log.info("Client connected: %s:%d", *addr)
                serve_client(client_sock, addr, router, client_timeout)
                log.info("Client %s:%d disconnected.", *addr)
        except KeyboardInterrupt:
            log.info("Server stopped by user.")


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


def serve_client(
    client_sock: socket.socket,
    addr: tuple[str, int],
    router: Router,
    timeout: float | None = DEFAULT_CLIENT_TIMEOUT,
) -> None:
    """Serve one connected client until it leaves or a fatal error."""
    with client_sock:
        client_sock.settimeout(timeout)
        while True:
            try:
                request = receive_message(client_sock)
            except MalformedMessageError as exc:
                if not _try_send(client_sock, error(str(exc)), addr):
                    break
                continue
            except MessageTooLargeError as exc:
                _try_send(client_sock, error(str(exc)), addr)
                break
            except ConnectionError:
                break
            except socket.timeout:
                log.warning("Client %s timed out; closing.", addr)
                break
            except OSError as exc:
                log.warning("Socket error with %s: %s", addr, exc)
                break

            log.debug("Request from %s: %s", addr, request)
            response = handle_request(request, router)
            if not _try_send(client_sock, response, addr):
                break


def _try_send(
    sock: socket.socket, response: dict[str, Any], addr: tuple[str, int]
) -> bool:
    """Send *response*; return False if the connection is unusable."""
    try:
        send_message(sock, response)
    except OSError as exc:
        log.warning("Failed to send response to %s: %s", addr, exc)
        return False
    return True
