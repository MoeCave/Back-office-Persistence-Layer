"""TCP server: concurrent clients over asyncio streams.

Servidor TCP concurrente de alto rendimiento basado en flujos de asyncio.
Arquitectura híbrida de dos niveles:
1. Capa de red reactiva no bloqueante (Event Loop en el hilo principal):
   - Acepta conexiones simultáneas con ``asyncio.start_server``.
   - Control de admisión mediante ``asyncio.Semaphore(max_connections)``.
   - Timeouts de inactividad de clientes y protección contra slow-writers.
   - Handshake de autenticación mutua X.509 y cifrado AES-256-GCM.
2. Capa de persistencia aislada en hilos trabajadores (ThreadPoolExecutor):
   - Despacha consultas síncronas de base de datos a hilos 'db-worker-*'.
   - Cada hilo abre su propia sesión de SQLAlchemy mediante UnitOfWork,
     evitando condiciones de carrera y bloqueos del bucle de eventos.
3. Apagado limpio y ordenado (Graceful Shutdown):
   - Cancela clientes activos, cierra sockets y drena el pool de conexiones.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Any

from src.common.crypto import CipherIntegrityError, CryptoError, SessionCipher
from src.common.handshake import (
    ServerSecurityConfig,
    perform_server_handshake_async,
)
from src.common.protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ErrorCode,
    MalformedMessageError,
    MessageTooLargeError,
    error,
    read_encrypted_message,
    read_message,
    validate_request,
    write_encrypted_message,
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
    security: ServerSecurityConfig | None = None,
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
                security=security,
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

        mode_label = (
            "secure (mutual X.509 + AES-256-GCM)"
            if security is not None
            else "plaintext"
        )
        log.info(
            "Listening on %s:%d [%s] (workers=%d, max_conn=%d, "
            "idle_timeout=%.1fs).",
            bound_host,
            bound_port,
            mode_label,
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
    security: ServerSecurityConfig | None = None,
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
                reader,
                writer,
                router,
                executor,
                client_timeout,
                write_timeout,
                security=security,
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
                    security=security,
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
    security: ServerSecurityConfig | None = None,
) -> None:
    """Run the optional mutual handshake and request/response loop."""
    peer = writer.get_extra_info("peername")
    loop = asyncio.get_running_loop()
    log.info("Client connected: %s", peer)
    cipher: SessionCipher | None = None

    if security is not None:
        try:
            session = await perform_server_handshake_async(
                reader,
                writer,
                security,
                executor=executor,
            )
            cipher = session.cipher
            log.info(
                "Mutual handshake succeeded with %s (CN=%r, fp=%s...)",
                peer,
                session.peer_common_name,
                session.peer_fingerprint_sha256[:16],
            )
        except TimeoutError:
            log.warning("Handshake timed out for %s", peer)
            await _try_write(
                writer,
                error("Handshake timed out.", ErrorCode.AUTH_FAILED),
                peer,
                write_timeout,
            )
            return
        except (
            CryptoError,
            MalformedMessageError,
            MessageTooLargeError,
        ) as exc:
            log.warning("Handshake rejected for %s: %s", peer, exc)
            await _try_write(
                writer,
                error(
                    f"Mutual authentication failed: {exc}",
                    ErrorCode.AUTH_FAILED,
                ),
                peer,
                write_timeout,
            )
            return
        except ConnectionError:
            log.info("Client %s disconnected during handshake", peer)
            return

    while True:
        try:
            if cipher is not None:
                request = await asyncio.wait_for(
                    read_encrypted_message(reader, cipher),
                    timeout=client_timeout,
                )
            else:
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
        except CipherIntegrityError as exc:
            log.warning("Cipher integrity failure from %s: %s", peer, exc)
            await _try_write(
                writer,
                error(
                    f"Encrypted frame integrity check failed: {exc}",
                    ErrorCode.INTEGRITY_ERROR,
                ),
                peer,
                write_timeout,
                cipher=cipher,
            )
            break
        except MalformedMessageError as exc:
            err_resp = error(str(exc))
            if not await _try_write(
                writer, err_resp, peer, write_timeout, cipher=cipher
            ):
                break
            continue
        except MessageTooLargeError as exc:
            await _try_write(
                writer, error(str(exc)), peer, write_timeout, cipher=cipher
            )
            break
        except ConnectionError:
            break

        log.debug("Request from %s: %s", peer, request)
        response = await loop.run_in_executor(
            executor, handle_request, request, router
        )
        if not await _try_write(
            writer, response, peer, write_timeout, cipher=cipher
        ):
            break


async def _try_write(
    writer: asyncio.StreamWriter,
    response: dict[str, Any],
    peer: Any,
    write_timeout: float = DEFAULT_WRITE_TIMEOUT,
    cipher: SessionCipher | None = None,
) -> bool:
    """Write *response* within *write_timeout*; return False on failure."""
    try:
        coro = (
            write_encrypted_message(writer, cipher, response)
            if cipher is not None
            else write_message(writer, response)
        )
        await asyncio.wait_for(coro, timeout=write_timeout)
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
