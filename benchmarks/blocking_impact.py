"""Reproducible experiment: event-loop blocking vs. thread offloading.

Simulates N concurrent TCP clients sending length-prefixed JSON requests
against two asyncio server modes:
  1. ``blocking``: calls ``time.sleep`` directly inside the coroutine,
     simulating a synchronous DB driver (psycopg2/sqlite3) freezing the loop.
  2. ``threaded``: delegates the blocking call via ``asyncio.to_thread``,
     allowing the event loop to multiplex network I/O concurrently.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import struct
import time
from typing import Literal

HEADER_FORMAT = "!I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
Mode = Literal["blocking", "threaded"]


def _pack_frame(payload: dict[str, object]) -> bytes:
    """Encode *payload* as a 4-byte big-endian length-prefixed UTF-8 frame."""
    body = json.dumps(payload).encode("utf-8")
    return struct.pack(HEADER_FORMAT, len(body)) + body


async def _read_frame(reader: asyncio.StreamReader) -> dict[str, object]:
    """Read one length-prefixed JSON frame from *reader*."""
    raw_header = await reader.readexactly(HEADER_SIZE)
    (length,) = struct.unpack(HEADER_FORMAT, raw_header)
    raw_body = await reader.readexactly(length)
    return json.loads(raw_body.decode("utf-8"))


def _simulate_sync_db_query(delay: float) -> dict[str, object]:
    """Simulate a synchronous, blocking database query."""
    time.sleep(delay)
    return {"status": "ok", "db_delay_s": delay}


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    mode: Mode,
    db_delay: float,
) -> None:
    """Serve a single request in either blocking or thread-offloaded mode."""
    try:
        request = await _read_frame(reader)
        if mode == "blocking":
            result = _simulate_sync_db_query(db_delay)
        else:
            result = await asyncio.to_thread(_simulate_sync_db_query, db_delay)
        response = {
            "success": True,
            "data": {"echo": request.get("action"), **result},
        }
        writer.write(_pack_frame(response))
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _run_client(host: str, port: int, client_id: int) -> float:
    """Connect, send one request, await the reply, and return latency (s)."""
    start = time.perf_counter()
    reader, writer = await asyncio.open_connection(host, port)
    try:
        payload: dict[str, object] = {
            "resource": "fighters",
            "action": "list",
            "payload": {"client_id": client_id},
        }
        writer.write(_pack_frame(payload))
        await writer.drain()
        response = await _read_frame(reader)
        if not response.get("success"):
            raise RuntimeError(f"Unexpected error response: {response}")
    finally:
        writer.close()
        await writer.wait_closed()
    return time.perf_counter() - start


async def run_experiment(
    mode: Mode, clients: int, db_delay: float
) -> tuple[float, list[float]]:
    """Start an ephemeral server and measure *clients* concurrent requests."""
    server = await asyncio.start_server(
        lambda r, w: _handle_client(r, w, mode, db_delay),
        host="127.0.0.1",
        port=0,
    )
    sockets = server.sockets
    if not sockets:
        raise RuntimeError("Server failed to bind an ephemeral port.")
    host, port = sockets[0].getsockname()[:2]

    wall_start = time.perf_counter()
    async with server:
        tasks = [
            asyncio.create_task(_run_client(host, port, idx))
            for idx in range(clients)
        ]
        latencies = await asyncio.gather(*tasks)
    wall_elapsed = time.perf_counter() - wall_start
    return wall_elapsed, list(latencies)


def _print_report(
    mode: Mode,
    clients: int,
    db_delay: float,
    wall_time: float,
    latencies: list[float],
) -> None:
    """Format and print latency statistics for one experiment run."""
    ordered = sorted(latencies)
    p95_index = max(0, int(0.95 * len(ordered)) - 1)
    print(
        f"\n--- Mode: {mode.upper()} "
        f"(N={clients}, db_delay={db_delay:.2f}s) ---"
    )
    print(f"  Total wall-clock time : {wall_time:.4f} s")
    print(f"  Min client latency    : {ordered[0]:.4f} s")
    print(f"  Mean client latency   : {statistics.mean(ordered):.4f} s")
    print(f"  P95 client latency    : {ordered[p95_index]:.4f} s")
    print(f"  Max client latency    : {ordered[-1]:.4f} s")


async def main() -> None:
    """Parse CLI arguments and execute both benchmark modes sequentially."""
    parser = argparse.ArgumentParser(
        description="Measure event-loop blocking vs. asyncio.to_thread."
    )
    parser.add_argument(
        "--clients",
        type=int,
        default=10,
        help="Number of concurrent clients (default: 10)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.20,
        help="Simulated synchronous DB latency in seconds (default: 0.20)",
    )
    args = parser.parse_args()

    for mode in ("blocking", "threaded"):
        wall, lats = await run_experiment(mode, args.clients, args.delay)
        _print_report(mode, args.clients, args.delay, wall, lats)


if __name__ == "__main__":
    asyncio.run(main())
