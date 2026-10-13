"""
server/app.py — TCP server entry point.

Listens for one client at a time, receives framed JSON requests,
routes them through the Router, and sends framed JSON responses.

Usage:
    python server.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import logging
import socket
import sys

from src.server.protocol import receive_message, send_message, validate_request, error
from src.server.router import Router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SERVER] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
BACKLOG = 1   # only one client at a time


def run_server(host: str, port: int, session_factory) -> None:
    """Start the blocking TCP server and serve one client at a time."""
    router = Router(session_factory)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((host, port))
        server_sock.listen(BACKLOG)
        log.info("Listening on %s:%d (one client at a time).", host, port)

        while True:
            log.info("Waiting for a client connection…")
            client_sock, addr = server_sock.accept()
            log.info("Client connected: %s:%d", *addr)
            _serve_client(client_sock, addr, router)
            log.info("Client %s:%d disconnected.", *addr)


def _serve_client(
    client_sock: socket.socket,
    addr: tuple[str, int],
    router: Router,
) -> None:
    """Handle a connected client until they disconnect or an error occurs."""
    with client_sock:
        while True:
            try:
                request = receive_message(client_sock)
            except ConnectionError:
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to read message from %s: %s", addr, exc)
                break

            log.debug("Request from %s: %s", addr, request)

            validation_error = validate_request(request)
            if validation_error:
                response = error(validation_error)
            else:
                response = router.handle(request)

            try:
                send_message(client_sock, response)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to send response to %s: %s", addr, exc)
                break
