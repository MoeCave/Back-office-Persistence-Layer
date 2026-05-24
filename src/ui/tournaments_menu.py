"""
Tournaments submenu — CRUD, searches, and relationship management.

Relationships demonstrated:
  - 1:N  Tournament → Tatami
  - 1:N  Tournament → Match
  - N:M+attrs  Tournament ↔ Fighter ↔ Category (registrations)
"""

from __future__ import annotations

from datetime import datetime

from rich.table import Table

from src.domain.models import Tournament, Tatami
from src.domain.repositories import UnitOfWork

from .console import console
from .helpers import (
    ask, ask_bool, ask_float_optional, ask_int_optional, ask_optional,
    empty_table_msg, error, info, make_table, pause, rel_badge,
    section, success,
)


# ── Table renderers ────────────────────────────────────────────────────────────

def _tournament_table(tournaments: list[Tournament], title: str = "Tournaments") -> Table:
    t = make_table("ID", "Name", "Location", "Start", "End",
                   "Max fighters", "Created", title=title)
    for t_obj in tournaments:
        t.add_row(
            str(t_obj.tournament_id),
            t_obj.name,
            t_obj.location or "—",
            str(t_obj.start_date.date()) if t_obj.start_date else "—",
            str(t_obj.end_date.date())   if t_obj.end_date   else "—",
            str(t_obj.max_fighters or "—"),
            str(t_obj.created_at.date()) if t_obj.created_at else "—",
        )
    return t


def _tatami_table(tatamis: list[Tatami]) -> Table:
    t = make_table("ID", "Name", "Mat #", "Area (m²)", "Active",
                   title=f"Tatamis  {rel_badge('1:N')}")
    for ta in tatamis:
        t.add_row(
            str(ta.tatami_id),
            ta.name,
            str(ta.mat_number or "—"),
            str(ta.area_size or "—"),
            "✓" if ta.is_active else "✗",
        )
    return t


# ── CRUD ───────────────────────────────────────────────────────────────────────

def _create(uow: UnitOfWork) -> None:
    section("Create Tournament")
    name = ask("Tournament name")
    if not name:
        error("Name is required.")
        return

    location    = ask_optional("Location")
    start_str   = ask_optional("Start date (YYYY-MM-DD)")
    end_str     = ask_optional("End date   (YYYY-MM-DD)")
    max_fighters = ask_int_optional("Max fighters")

    start_date = end_date = None
    for val, attr, lbl in [(start_str, "start_date", "Start"), (end_str, "end_date", "End")]:
        if val:
            try:
                dt = datetime.strptime(val, "%Y-%m-%d")
                if attr == "start_date":
                    start_date = dt
                else:
                    end_date = dt
            except ValueError:
                console.print(f"[warning]  Invalid {lbl} date — skipped.[/]")

    t = Tournament(
        name=name,
        location=location,
        start_date=start_date,
        end_date=end_date,
        max_fighters=max_fighters,
    )
    uow.tournaments.add(t)
    uow.commit()
    success(f"Tournament created — ID {t.tournament_id}: {t.name}")


def _list_all(uow: UnitOfWork) -> None:
    section("All Tournaments")
    tournaments = uow.tournaments.get_all()
    if not tournaments:
        empty_table_msg("tournaments")
    else:
        console.print(_tournament_table(tournaments))


def _read_by_id(uow: UnitOfWork) -> None:
    section("Get Tournament by ID (+ relationships)")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return

    t = uow.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    console.print(_tournament_table([t], title=f"Tournament #{tid}"))

    # ── 1:N Tatamis ────────────────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]1:N[/] — Tatamis  {rel_badge('1:N')}")
    if t.tatamis:
        console.print(_tatami_table(t.tatamis))
    else:
        info("  No tatamis configured.")

    # ── 1:N Matches ────────────────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]1:N[/] — Matches  {rel_badge('1:N')}")
    matches = uow.matches.get_by_tournament(tid)
    info(f"  Total matches: {len(matches)}")

    # ── N:M+attrs Registrations ────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]N:M+attrs[/] — Registrations  {rel_badge('N:M+attrs')}")
    regs = uow.registrations.get_by_tournament(tid)
    pending = [r for r in regs if not r.is_approved]
    info(f"  Total registrations: {len(regs)}   Pending approval: {len(pending)}")


def _update(uow: UnitOfWork) -> None:
    section("Update Tournament")
    tid = ask_int_optional("Tournament ID to update")
    if tid is None:
        return

    t = uow.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    info(f"  Editing: {t.name}")
    t.name     = ask(f"Name [{t.name}]",              default=t.name) or t.name
    t.location = ask(f"Location [{t.location or ''}]",default=t.location or "") or None
    max_raw    = ask(f"Max fighters [{t.max_fighters or ''}]",
                     default=str(t.max_fighters or ""))
    t.max_fighters = int(max_raw) if max_raw.isdigit() else t.max_fighters

    uow.tournaments.update(t)
    uow.commit()
    success(f"Tournament #{tid} updated.")


def _delete(uow: UnitOfWork) -> None:
    section("Delete Tournament")
    tid = ask_int_optional("Tournament ID to delete")
    if tid is None:
        return

    t = uow.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    if not ask_bool(f"Delete '{t.name}' (cascades to tatamis, matches, registrations)?", False):
        info("Cancelled.")
        return

    uow.tournaments.delete(t)
    uow.commit()
    success(f"Tournament #{tid} deleted.")


# ── Searches ───────────────────────────────────────────────────────────────────

def _search_by_name(uow: UnitOfWork) -> None:
    section("Search by Name")
    name = ask("Name (partial match)")
    results = uow.tournaments.get_by_name(name)
    if not results:
        info(f"No tournaments matching '{name}'.")
    else:
        console.print(_tournament_table(results))


def _search_by_location(uow: UnitOfWork) -> None:
    section("Filter by Location")
    loc = ask("Location (partial match)")
    results = uow.tournaments.get_by_location(loc)
    if not results:
        info(f"No tournaments in '{loc}'.")
    else:
        console.print(_tournament_table(results))


def _list_active(uow: UnitOfWork) -> None:
    section("Active / Upcoming Tournaments")
    results = uow.tournaments.get_active_tournaments()
    if not results:
        info("No active tournaments.")
    else:
        console.print(_tournament_table(results, title="Active / Upcoming"))


def _list_upcoming(uow: UnitOfWork) -> None:
    section("Upcoming Tournaments (not yet started)")
    results = uow.tournaments.get_upcoming()
    if not results:
        info("No upcoming tournaments.")
    else:
        console.print(_tournament_table(results, title="Upcoming"))


# ── 1:N Tatami management ──────────────────────────────────────────────────────

def _add_tatami(uow: UnitOfWork) -> None:
    section(f"Add Tatami to Tournament  {rel_badge('1:N')}")
    info("  Relationship type: 1:N — a tournament owns multiple tatamis.")

    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    t = uow.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    info(f"  Tournament: {t.name}")
    name       = ask("Tatami name (e.g. Tatami A)")
    if not name:
        error("Name is required.")
        return
    mat_number = ask_int_optional("Mat number")
    area_size  = ask_float_optional("Area size (m²)")
    is_active  = ask_bool("Active?", default=True)

    tatami = uow.tournaments.add_tatami_to_tournament(
        tid, name=name, mat_number=mat_number,
        area_size=area_size, is_active=is_active,
    )
    uow.commit()
    success(f"Tatami '{tatami.name}' (ID {tatami.tatami_id}) added to tournament '{t.name}'.")


def _list_tatamis(uow: UnitOfWork) -> None:
    section(f"Tatamis by Tournament  {rel_badge('1:N')}")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    t = uow.tournaments.get(tid)
    if t is None:
        error(f"No tournament with ID {tid}.")
        return

    info(f"  Tournament: {t.name}")
    if t.tatamis:
        console.print(_tatami_table(t.tatamis))
    else:
        info("  No tatamis configured for this tournament.")


# ── Submenu ────────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all tournaments",                           _list_all),
    ("Get tournament by ID (+ relationships)",         _read_by_id),
    ("Create tournament",                              _create),
    ("Update tournament",                              _update),
    ("Delete tournament",                              _delete),
    ("Search by name",                                 _search_by_name),
    ("Filter by location",                             _search_by_location),
    ("Active / upcoming tournaments",                  _list_active),
    ("Not-yet-started tournaments",                    _list_upcoming),
    (f"Add tatami to tournament  [rel_1_n](1:N)[/]",  _add_tatami),
    (f"List tatamis of tournament  [rel_1_n](1:N)[/]",_list_tatamis),
]


def tournaments_menu(session_factory) -> None:
    while True:
        section("Tournaments")
        for i, (label, _) in enumerate(_MENU_ITEMS, start=1):
            console.print(f"  [muted]{i:>2}.[/] {label}")
        console.print(f"  [muted] 0.[/] Back")

        choice = ask_int_optional("Choose")
        if choice is None or choice == 0:
            break
        if not (1 <= choice <= len(_MENU_ITEMS)):
            error("Invalid option.")
            continue

        _, handler = _MENU_ITEMS[choice - 1]
        try:
            with UnitOfWork(session_factory=session_factory) as uow:
                handler(uow)
        except Exception as exc:
            error(f"Unexpected error: {exc}")

        pause()
