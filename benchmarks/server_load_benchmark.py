"""End-to-end concurrency benchmark against the real asyncio server.

Measures wall-clock duration, throughput, and client latency percentiles
using ``AsyncServerGateway`` against ``run_server``, ``Router``,
``FighterService``, and a real SQLAlchemy SQLite database.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import statistics
import sys
import tempfile
import time
from typing import Any
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.client.async_gateway import AsyncServerGateway  # noqa: E402
from src.domain.db import Base  # noqa: E402
import src.domain.models  # noqa: E402, F401 - registers ORM metadata
from src.server.app import run_server  # noqa: E402
from src.server.router import Router  # noqa: E402


def _create_temp_db(db_path: Path):
    """Build a thread-safe SQLite engine and sessionmaker on *db_path*."""
    url = f"sqlite:///{db_path.as_posix()}"
    eng = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(eng)
    return eng, sessionmaker(bind=eng, autoflush=False)


async def _seed_fighters(host: str, port: int, count: int = 25) -> None:
    """Populate realistic fighter records via the real TCP protocol."""
    async with AsyncServerGateway(host, port) as gw:
        for idx in range(count):
            await gw.resource("fighters").call(
                "create",
                {
                    "first_name": f"Fighter{idx}",
                    "last_name": f"Bench{idx}",
                    "birth_date": "1998-05-15",
                },
            )


async def _client_worker(
    host: str,
    port: int,
    requests_per_client: int,
) -> list[float]:
    """Open one persistent connection and time sequential list calls."""
    latencies: list[float] = []
    async with AsyncServerGateway(host, port) as gw:
        for _ in range(requests_per_client):
            t0 = time.perf_counter()
            rows = await gw.resource("fighters").call("list")
            elapsed = time.perf_counter() - t0
            if not isinstance(rows, list):
                raise RuntimeError(f"Unexpected payload: {rows!r}")
            latencies.append(elapsed)
    return latencies


async def _measure_scenario(
    session_factory: Any,
    clients: int,
    requests_per_client: int,
    db_workers: int,
    db_delay: float,
    block_event_loop: bool,
) -> dict[str, float]:
    """Run one benchmark scenario and return aggregated metrics."""
    stop_event = asyncio.Event()
    started = asyncio.Event()
    bound: dict[str, Any] = {}

    def _on_started(host: str, port: int) -> None:
        bound["host"] = host
        bound["port"] = port
        started.set()

    orig_router_handle = Router.handle

    def _delayed_router_handle(
        self: Router, request: dict[str, Any]
    ) -> dict[str, Any]:
        if db_delay > 0:
            time.sleep(db_delay)
        return orig_router_handle(self, request)

    async def _blocking_run_in_executor(
        _executor: Any, fn: Any, *args: Any
    ) -> Any:
        return fn(*args)

    loop = asyncio.get_running_loop()
    server_task = asyncio.create_task(
        run_server(
            host="127.0.0.1",
            port=0,
            session_factory=session_factory,
            db_workers=db_workers,
            stop_event=stop_event,
            on_started=_on_started,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5.0)

    try:
        with patch.object(Router, "handle", _delayed_router_handle):
            if block_event_loop:
                patcher = patch.object(
                    loop, "run_in_executor", _blocking_run_in_executor
                )
                patcher.start()
            else:
                patcher = None

            try:
                wall_start = time.perf_counter()
                nested = await asyncio.gather(
                    *(
                        _client_worker(
                            bound["host"],
                            bound["port"],
                            requests_per_client,
                        )
                        for _ in range(clients)
                    )
                )
                wall_time = time.perf_counter() - wall_start
            finally:
                if patcher is not None:
                    patcher.stop()
    finally:
        stop_event.set()
        await asyncio.wait_for(server_task, timeout=5.0)

    all_latencies = sorted(lat for sub in nested for lat in sub)
    total_reqs = len(all_latencies)
    p95_idx = max(0, int(0.95 * total_reqs) - 1)
    return {
        "wall_s": wall_time,
        "rps": total_reqs / wall_time,
        "mean_ms": statistics.mean(all_latencies) * 1000.0,
        "p95_ms": all_latencies[p95_idx] * 1000.0,
        "max_ms": all_latencies[-1] * 1000.0,
    }


async def main() -> None:
    """Seed temporary DB, execute scenarios, and print Markdown table."""
    parser = argparse.ArgumentParser(
        description="End-to-end real server concurrency benchmark."
    )
    parser.add_argument(
        "--clients",
        type=int,
        default=20,
        help="Concurrent TCP clients (default: 20)",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=3,
        help="Sequential requests per client (default: 3)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.10,
        help="Simulated DB I/O delay per query in seconds (default: 0.10)",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "bench_real_server.db"
        eng, session_factory = _create_temp_db(db_path)
        try:
            stop_seed = asyncio.Event()
            ready_seed = asyncio.Event()
            seed_bound: dict[str, Any] = {}

            def _on_seed(host: str, port: int) -> None:
                seed_bound["host"] = host
                seed_bound["port"] = port
                ready_seed.set()

            seed_srv = asyncio.create_task(
                run_server(
                    host="127.0.0.1",
                    port=0,
                    session_factory=session_factory,
                    stop_event=stop_seed,
                    on_started=_on_seed,
                )
            )
            await asyncio.wait_for(ready_seed.wait(), timeout=5.0)
            await _seed_fighters(seed_bound["host"], seed_bound["port"], 25)
            stop_seed.set()
            await asyncio.wait_for(seed_srv, timeout=5.0)

            scenarios = [
                ("Event-loop blocked", 1, args.delay, True),
                ("ThreadPool (workers=4)", 4, args.delay, False),
                ("ThreadPool (workers=10)", 10, args.delay, False),
                ("Pure SQLite ORM (w=10)", 10, 0.0, False),
            ]

            print(
                f"\nBenchmark: {args.clients} concurrent clients x "
                f"{args.requests} requests "
                f"({args.clients * args.requests} total ops)\n"
            )
            header = (
                "| Escenario | Wall (s) | Req/s | Media (ms) | "
                "P95 (ms) | Max (ms) |"
            )
            sep = "| :--- | :---: | :---: | :---: | :---: | :---: |"
            print(header)
            print(sep)
            for label, workers, delay, blocked in scenarios:
                metrics = await _measure_scenario(
                    session_factory=session_factory,
                    clients=args.clients,
                    requests_per_client=args.requests,
                    db_workers=workers,
                    db_delay=delay,
                    block_event_loop=blocked,
                )
                print(
                    f"| {label} | {metrics['wall_s']:.3f} | "
                    f"{metrics['rps']:.1f} | {metrics['mean_ms']:.1f} | "
                    f"{metrics['p95_ms']:.1f} | {metrics['max_ms']:.1f} |"
                )
        finally:
            eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
