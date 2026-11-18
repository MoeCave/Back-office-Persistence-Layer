"""Asynchronous TCP client gateway built on ``asyncio`` streams.

Pasarela cliente TCP asíncrona sobre flujos de ``asyncio``.
Proporciona :class:`AsyncServerGateway` para emitir peticiones JSON enmarcadas
concurrentes hacia el servidor TCP sin bloquear el bucle de eventos.

Si se proporciona :class:`~src.common.handshake.ClientSecurityConfig`,
``connect()`` realiza autenticación mutua X.509 y establece un canal de sesión
cifrado con AES-256-GCM.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

from src.common.crypto import CipherIntegrityError, SessionCipher
from src.common.handshake import (
    AuthenticatedSession,
    ClientSecurityConfig,
    perform_client_handshake_async,
)
from src.common.protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ErrorCode,
    read_encrypted_message,
    read_message,
    write_encrypted_message,
    write_message,
)

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_REQUEST_TIMEOUT = 30.0


class AsyncServerError(RuntimeError):
    """Raised when the server returns a ``success: false`` envelope."""

    def __init__(
        self,
        message: str,
        code: str = ErrorCode.INTERNAL_ERROR,
    ) -> None:
        super().__init__(f"[{code}] {message}")
        self.message = message
        self.code = code


class AsyncResourceProxy:
    """Convenience namespace bound to a single protocol resource."""

    def __init__(
        self,
        gateway: AsyncServerGateway,
        resource: str,
    ) -> None:
        self._gateway = gateway
        self._resource = resource

    async def call(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Send *action* with *payload* for the bound resource."""
        return await self._gateway.request(self._resource, action, payload)


class AsyncServerGateway:
    """Async context-managed TCP client speaking the length-prefixed JSON
    wire protocol (optionally protected with mutual PKI + AES-256-GCM).
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        security: ClientSecurityConfig | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.security = security
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._session: AuthenticatedSession | None = None
        self._cipher: SessionCipher | None = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Return ``True`` while an open TCP stream is held."""
        return self._writer is not None and not self._writer.is_closing()

    @property
    def session(self) -> AuthenticatedSession | None:
        """Return the authenticated session metadata when security is
        enabled."""
        return self._session

    def resource(self, name: str) -> AsyncResourceProxy:
        """Return an :class:`AsyncResourceProxy` for *name*."""
        return AsyncResourceProxy(self, name)

    async def connect(self) -> None:
        """Open the TCP connection and perform optional mutual handshake."""
        if self.is_connected:
            return
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.connect_timeout,
        )
        try:
            if self.security is not None:
                session = await perform_client_handshake_async(
                    reader, writer, self.security
                )
                self._session = session
                self._cipher = session.cipher
            else:
                self._session = None
                self._cipher = None
        except Exception:
            if not writer.is_closing():
                writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
            except (OSError, TimeoutError):
                pass
            self._session = None
            self._cipher = None
            raise

        self._reader = reader
        self._writer = writer

    async def close(self) -> None:
        """Close the underlying TCP stream cleanly."""
        writer = self._writer
        self._reader = None
        self._writer = None
        self._session = None
        self._cipher = None
        if writer is None:
            return
        if not writer.is_closing():
            writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
        except (OSError, TimeoutError):
            pass

    async def __aenter__(self) -> AsyncServerGateway:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def request(
        self,
        resource: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Send one request envelope and return the ``data`` field.

        Serialises concurrent callers sharing the same TCP socket via
        an internal :class:`asyncio.Lock` so request/response frames
        never interleave on the wire.
        """
        if self._reader is None or self._writer is None:
            raise ConnectionError("Gateway is not connected.")

        envelope: dict[str, Any] = {
            "resource": resource,
            "action": action,
            "payload": payload or {},
        }
        try:
            async with self._lock:
                if self._cipher is not None:
                    await asyncio.wait_for(
                        write_encrypted_message(
                            self._writer, self._cipher, envelope
                        ),
                        timeout=self.request_timeout,
                    )
                    response = await asyncio.wait_for(
                        read_encrypted_message(self._reader, self._cipher),
                        timeout=self.request_timeout,
                    )
                else:
                    await asyncio.wait_for(
                        write_message(self._writer, envelope),
                        timeout=self.request_timeout,
                    )
                    response = await asyncio.wait_for(
                        read_message(self._reader),
                        timeout=self.request_timeout,
                    )
        except CipherIntegrityError as exc:
            raise AsyncServerError(
                f"Encrypted frame integrity check failed: {exc}",
                ErrorCode.INTEGRITY_ERROR,
            ) from exc

        if not isinstance(response, dict):
            raise AsyncServerError(
                "Invalid response envelope from server.",
                ErrorCode.INTERNAL_ERROR,
            )
        if not response.get("success"):
            raise AsyncServerError(
                str(response.get("error") or "Unknown server error."),
                str(response.get("error_code") or ErrorCode.INTERNAL_ERROR),
            )
        return response.get("data")
