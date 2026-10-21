"""
client/ui/tournaments_menu.py — Tournaments submenu adapted for the TCP client.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table

from src.client.gateway import ServerGateway, ServerError
from src.client.ui.console import console
from src.client.ui.helpers import run_handler
from src.client.ui.helpers import (
    ask,
    ask_bool,
    ask_float_optional,
    ask_int_optional,
    ask_optional,
    empty_table_msg,
    error,
    info,
    make_table,
    pause,
    rel_badge,
    section,
    success,
)

# ── Table renderers ──────────────────────────────────────────────────────────


def _tournament_table(
    tournaments: list[dict[str, Any]], title: str = "Tournaments"
) -> Table:
    t = make_table(
        "ID",
        "Name",
        "Location",
        "Start",
        "End",
        "Max fighters",
        "Created",
        title=title,
    )
    for t_obj in tournaments:
        t.add_row(
            str(t_obj.get("tournament_id", "—")),
            t_obj.get("name", "—"),
            t_obj.get("location") or "—",
            (t_obj.get("start_date") or "—")[:10],
            (t_obj.get("end_date") or "—")[:10],
            str(t_obj.get("max_fighters") or "—"),
            (t_obj.get("created_at") or "—")[:10],
        )
    return t


def _tatami_table(tatamis: list[dict[str, Any]]) -> Table:
    t = make_table(
        "ID",
        "Name",
        "Mat #",
        "Area (m²)",
        "Active",
        title=f"Tatamis  {rel_badge('1:N')}",
    )
    for ta in tatamis:
        t.add_row(
            str(ta.get("tatami_id", "—")),
            ta.get("name", "—"),
            str(ta.get("mat_number") or "—"),
            str(ta.get("area_size") or "—"),
            "✓" if ta.get("is_active") else "✗",
        )
    return t


# ── CRUD ─────────────────────────────────────────────────────────────────────


def _create(gw: ServerGateway) -> None:
    section("Create Tournament")
    name = ask("Tournament name")
    if not name:
        error("Name is required.")
        return

    location = ask_optional("Location")
    start_str = ask_optional("Start date (YYYY-MM-DD)")
    end_str = ask_optional("End date   (YYYY-MM-DD)")
    max_fighters = ask_int_optional("Max fighters")

    try:
        t = gw.tournaments.create(
            name=name,
            location=location,
            start_date=start_str,
            end_date=end_str,
            max_fighters=max_fighters,
        )
        success(f"Tournament created — ID {t['tournament_id']}: {t['name']}")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _list_all(gw: ServerGateway) -> None:
    section("All Tournaments")
    tournaments = gw.tournaments.list_all()
    if not tournaments:
        empty_table_msg("tournaments")
    else:
        console.print(_tournament_table(tournaments))


def _read_by_id(gw: ServerGateway) -> None:
    section("Get Tournament by ID (+ relationships)")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return

    t = gw.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    console.print(_tournament_table([t], title=f"Tournament #{tid}"))

    # ── 1:N Tatamis ──────────────────────────────────────────────────────────
    console.print(
        f"\n  Relationship [bold]1:N[/] — Tatamis  {rel_badge('1:N')}"
    )
    tatamis = t.get("tatamis", [])
    if tatamis:
        console.print(_tatami_table(tatamis))
    else:
        info("  No tatamis configured.")

    # ── 1:N Matches ──────────────────────────────────────────────────────────
    console.print(
        f"\n  Relationship [bold]1:N[/] — Matches  {rel_badge('1:N')}"
    )
    info(f"  Total matches: {t.get('total_matches', 0)}")

    # ── N:M+attrs Registrations ──────────────────────────────────────────────
    console.print(
        "\n  Relationship [bold]N:M+attrs[/] — Registrations  "
        f"{rel_badge('N:M+attrs')}"
    )
    info(
        f"  Total registrations: {t.get('total_registrations', 0)}   "
        f"Pending approval: {t.get('pending_registrations', 0)}"
    )


def _update(gw: ServerGateway) -> None:
    section("Update Tournament")
    tid = ask_int_optional("Tournament ID to update")
    if tid is None:
        return

    t = gw.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    info(f"  Editing: {t['name']}")
    new_name = ask(f"Name [{t['name']}]", default=t["name"]) or t["name"]
    new_loc = (
        ask(
            f"Location [{t.get('location') or ''}]",
            default=t.get("location") or "",
        )
        or None
    )
    max_raw = ask(
        f"Max fighters [{t.get('max_fighters') or ''}]",
        default=str(t.get("max_fighters") or ""),
    )
    new_max = int(max_raw) if max_raw.isdigit() else t.get("max_fighters")

    try:
        gw.tournaments.update(
            tid, name=new_name, location=new_loc, max_fighters=new_max
        )
        success(f"Tournament #{tid} updated.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _delete(gw: ServerGateway) -> None:
    section("Delete Tournament")
    tid = ask_int_optional("Tournament ID to delete")
    if tid is None:
        return

    t = gw.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    if not ask_bool(
        f"Delete '{t['name']}' (cascades to tatamis, matches, registrations)?",
        False,
    ):
        info("Cancelled.")
        return

    try:
        gw.tournaments.delete(tid)
        success(f"Tournament #{tid} deleted.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


# ── Searches ─────────────────────────────────────────────────────────────────


def _search_by_name(gw: ServerGateway) -> None:
    section("Search by Name")
    name = ask("Name (partial match)")
    results = gw.tournaments.get_by_name(name)
    if not results:
        info(f"No tournaments matching '{name}'.")
    else:
        console.print(_tournament_table(results))


def _search_by_location(gw: ServerGateway) -> None:
    section("Filter by Location")
    loc = ask("Location (partial match)")
    results = gw.tournaments.get_by_location(loc)
    if not results:
        info(f"No tournaments in '{loc}'.")
    else:
        console.print(_tournament_table(results))


def _list_active(gw: ServerGateway) -> None:
    section("Active / Upcoming Tournaments")
    results = gw.tournaments.get_active_tournaments()
    if not results:
        info("No active tournaments.")
    else:
        console.print(_tournament_table(results, title="Active / Upcoming"))


def _list_upcoming(gw: ServerGateway) -> None:
    section("Upcoming Tournaments (not yet started)")
    results = gw.tournaments.get_upcoming()
    if not results:
        info("No upcoming tournaments.")
    else:
        console.print(_tournament_table(results, title="Upcoming"))


# ── 1:N Tatami management ────────────────────────────────────────────────────


def _add_tatami(gw: ServerGateway) -> None:
    section(f"Add Tatami to Tournament  {rel_badge('1:N')}")
    info("  Relationship type: 1:N — a tournament owns multiple tatamis.")

    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    t = gw.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    info(f"  Tournament: {t['name']}")
    name = ask("Tatami name (e.g. Tatami A)")
    if not name:
        error("Name is required.")
        return
    mat_number = ask_int_optional("Mat number")
    area_size = ask_float_optional("Area size (m²)")
    is_active = ask_bool("Active?", default=True)

    try:
        tatami = gw.tournaments.add_tatami_to_tournament(
            tid,
            name=name,
            mat_number=mat_number,
            area_size=area_size,
            is_active=is_active,
        )
        success(
            f"Tatami '{tatami['name']}' (ID {tatami['tatami_id']}) "
            f"added to tournament '{t['name']}'."
        )
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _list_tatamis(gw: ServerGateway) -> None:
    section(f"Tatamis by Tournament  {rel_badge('1:N')}")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    t = gw.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    info(f"  Tournament: {t['name']}")
    tatamis = t.get("tatamis", [])
    if tatamis:
        console.print(_tatami_table(tatamis))
    else:
        info("  No tatamis configured for this tournament.")


# ── Submenu ──────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all tournaments", _list_all),
    ("Get tournament by ID (+ relationships)", _read_by_id),
    ("Create tournament", _create),
    ("Update tournament", _update),
    ("Delete tournament", _delete),
    ("Search by name", _search_by_name),
    ("Filter by location", _search_by_location),
    ("Active / upcoming tournaments", _list_active),
    ("Not-yet-started tournaments", _list_upcoming),
    ("Add tatami to tournament  [rel_1_n](1:N)[/]", _add_tatami),
    ("List tatamis of tournament  [rel_1_n](1:N)[/]", _list_tatamis),
]


def tournaments_menu(gw: ServerGateway) -> None:
    while True:
        section("Tournaments")
        for i, (label, _) in enumerate(_MENU_ITEMS, start=1):
            console.print(f"  [muted]{i:>2}.[/] {label}")
        console.print("  [muted] 0.[/] Back")

        choice = ask_int_optional("Choose")
        if choice is None or choice == 0:
            break
        if not (1 <= choice <= len(_MENU_ITEMS)):
            error("Invalid option.")
            continue

        _, handler = _MENU_ITEMS[choice - 1]
        run_handler(handler, gw)

        pause()
