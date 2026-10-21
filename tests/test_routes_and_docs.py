"""Consistency between the routing table and docs/PROTOCOL.md."""

from __future__ import annotations

import re
from pathlib import Path

from src.common.protocol import ErrorCode, VALID_RESOURCES
from src.server.routes import ROUTES

DOC = Path(__file__).resolve().parents[1] / "docs" / "PROTOCOL.md"


def _documented_actions() -> dict[str, set[str]]:
    """Parse the '### 4.x `resource`' tables of PROTOCOL.md."""
    documented: dict[str, set[str]] = {}
    current = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"### 4\.\d `(\w+)`", line)
        if heading:
            current = heading.group(1)
            documented[current] = set()
        elif current and (row := re.match(r"\| `(\w+)` \|", line)):
            documented[current].add(row.group(1))
        elif line.startswith("## 5."):
            break
    return documented


def test_routes_cover_every_valid_resource():
    assert set(ROUTES) == set(VALID_RESOURCES)


def test_every_route_is_documented_and_vice_versa():
    documented = _documented_actions()
    actual = {res: set(actions) for res, actions in ROUTES.items()}
    assert documented == actual


def test_every_error_code_is_documented():
    text = DOC.read_text(encoding="utf-8")
    codes = [
        value
        for name, value in vars(ErrorCode).items()
        if not name.startswith("_")
    ]
    assert all(f"`{code}`" in text for code in codes)
