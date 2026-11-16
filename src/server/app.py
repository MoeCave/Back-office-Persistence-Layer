"""TCP server: concurrent clients over asyncio streams.

The server accepts multiple concurrent TCP connections via
``asyncio.start_server``, enforces connection limits and I/O timeouts,
offloads synchronous routing and database work to a bounded
:class:`~concurrent.futures.ThreadPoolExecutor`, and replies
asynchronously.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Any
from collections.abc import Callable

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
DEFAULT_WRITE_TIMEOUT = 30.0
DEFAULT_CLOSE_TIMEOUT = 5.0
DEFAULT_DB_WORKERS = 10
DEFAULT_MAX_CONNECTIONS = 100

__all__ = [
    "DEFAULT_BACKLOG",
    "DEFAULT_CLIENT_TIMEOUT",
    "DEFAULT_CLOSE_TIMEOUT",
    "DEFAULT_DB_WORKERS",
    "DEFAULT_HOST",
    "DEFAULT_MAX_CONNECTIONS",
    "DEFAULT_PORT",
    "DEFAULT_WRITE_TIMEOUT",
    "handle_client",
    "handle_request",
    "run_server",
]


async def run_server(
    host: str,
    port: int,
    session_factory: Any,
    backlog: int = DEFAULT_BACKLOG,
    db_workers: int = DEFAULT_DB_WORKERS,
    client_timeout: float = DEFAULT_CLIENT_TIMEOUT,
    write_timeout: float = DEFAULT_WRITE_TIMEOUT,
    max_connections: int = DEFAULT_MAX_CONNECTIONS,
    stop_event: asyncio.Event | None = None,
    on_started: Callable[[str, int], None] | None = None,
) -> None:
    """Start the asyncio TCP server and serve until stopped or cancelled."""
    router = Router(session_factory)
    semaphore = asyncio.Semaphore(max_connections)
    active_tasks: set[asyncio.Task[Any]] = set()
    executor = ThreadPoolExecutor(
        max_workers=db_workers,
        thread_name_prefix="db-worker",
    )

    def _on_connect(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.create_task(
            handle_client(
                reader,
                writer,
                router,
                executor=executor,
                client_timeout=client_timeout,
                write_timeout=write_timeout,
                semaphore=semaphore,
            )
        )
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)

    server = await asyncio.start_server(
        _on_connect,
        host=host,
        port=port,
        backlog=backlog,
    )
    try:
        sockets = server.sockets
        if sockets:
            bound_host, bound_port = sockets[0].getsockname()[:2]
            if on_started is not None:
                on_started(bound_host, bound_port)
        else:
            bound_host, bound_port = host, port

        log.info(
            "Listening on %s:%d (workers=%d, max_conn=%d, "
            "idle_timeout=%.1fs).",
            bound_host,
            bound_port,
            db_workers,
            max_connections,
            client_timeout,
        )
        if stop_event is None:
            await server.serve_forever()
        else:
            await stop_event.wait()
    finally:
        server.close()
        await _shutdown_active_tasks(active_tasks)
        await server.wait_closed()
        executor.shutdown(wait=True)


async def _shutdown_active_tasks(
    active_tasks: set[asyncio.Task[Any]],
) -> None:
    """Cancel remaining client tasks and wait for their cleanup."""
    if not active_tasks:
        return
    pending = list(active_tasks)
    log.info("Cancelling %d active client task(s)...", len(pending))
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


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
    executor: ThreadPoolExecutor | None = None,
    client_timeout: float = DEFAULT_CLIENT_TIMEOUT,
    write_timeout: float = DEFAULT_WRITE_TIMEOUT,
    semaphore: asyncio.Semaphore | None = None,
) -> None:
    """Serve one connected client with bounded lifetime and fault isolation."""
    peer = writer.get_extra_info("peername")
    if semaphore is not None and semaphore.locked():
        log.warning("Max connections reached; rejecting %s", peer)
        await _close_writer(writer)
        return

    try:
        if semaphore is None:
            await _serve_session(
                reader, writer, router, executor, client_timeout, write_timeout
            )
        else:
            async with semaphore:
                await _serve_session(
                    reader,
                    writer,
                    router,
                    executor,
                    client_timeout,
                    write_timeout,
                )
    except Exception:  # noqa: BLE001 - isolate per-client failures
        log.exception("Unhandled error while serving client %s", peer)
    finally:
        await _close_writer(writer)
        log.info("Client disconnected: %s", peer)


async def _serve_session(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    router: Router,
    executor: ThreadPoolExecutor | None,
    client_timeout: float,
    write_timeout: float,
) -> None:
    """Run the request/response loop for an admitted client."""
    peer = writer.get_extra_info("peername")
    loop = asyncio.get_running_loop()
    log.info("Client connected: %s", peer)

    while True:
        try:
            request = await asyncio.wait_for(
                read_message(reader), timeout=client_timeout
            )
        except TimeoutError:
            log.info(
                "Client %s timed out after %.1fs of inactivity",
                peer,
                client_timeout,
            )
            break
        except MalformedMessageError as exc:
            err_resp = error(str(exc))
            if not await _try_write(writer, err_resp, peer, write_timeout):
                break
            continue
        except MessageTooLargeError as exc:
            await _try_write(writer, error(str(exc)), peer, write_timeout)
            break
        except ConnectionError:
            break

        log.debug("Request from %s: %s", peer, request)
        response = await loop.run_in_executor(
            executor, handle_request, request, router
        )
        if not await _try_write(writer, response, peer, write_timeout):
            break


async def _try_write(
    writer: asyncio.StreamWriter,
    response: dict[str, Any],
    peer: Any,
    write_timeout: float = DEFAULT_WRITE_TIMEOUT,
) -> bool:
    """Write *response* within *write_timeout*; return False on failure."""
    try:
        await asyncio.wait_for(
            write_message(writer, response), timeout=write_timeout
        )
    except TimeoutError:
        log.warning(
            "Write timeout (%.1fs) sending response to %s",
            write_timeout,
            peer,
        )
        return False
    except OSError as exc:
        log.warning("Failed to send response to %s: %s", peer, exc)
        return False
    return True


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    """Close *writer* gracefully without hanging on dead peers."""
    if not writer.is_closing():
        writer.close()
    try:
        await asyncio.wait_for(
            writer.wait_closed(), timeout=DEFAULT_CLOSE_TIMEOUT
        )
    except (OSError, TimeoutError):
        pass
