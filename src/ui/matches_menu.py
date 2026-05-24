"""
Matches submenu — CRUD and filter operations.

Relationships demonstrated:
  - N:M  Match references Fighter (blue/red/winner) — multiple FKs to same table
  - N:M  Match references Category and Tournament
  - 1:N  Tournament → Match (displayed from match side)
"""

from __future__ import annotations

from datetime import datetime

from rich.table import Table

from src.domain.models import Match
from src.domain.repositories import UnitOfWork

from .console import console
from .helpers import (
    ask, ask_bool, ask_float_optional, ask_int_optional, ask_optional,
    choose_from_list, empty_table_msg, error, info, make_table,
    pause, rel_badge, section, success,
)


# ── Table renderer ─────────────────────────────────────────────────────────────

def _match_table(matches: list[Match], title: str = "Matches") -> Table:
    t = make_table(
        "ID", "Tournament", "Category", "Round",
        "Blue fighter", "Red fighter", "Winner",
        "Method", "Duration (s)", "Scheduled",
        title=title,
    )
    for m in matches:
        t.add_row(
            str(m.match_id),
            str(m.tournament_id),
            str(m.category_id or "—"),
            str(m.round_number or "—"),
            str(m.blue_fighter_id or "—"),
            str(m.red_fighter_id  or "—"),
            str(m.winner_id       or "—"),
            m.win_method or "—",
            str(m.duration_seconds or "—"),
            str(m.scheduled_time)[:16] if m.scheduled_time else "—",
        )
    return t


# ── CRUD ───────────────────────────────────────────────────────────────────────

def _create(uow: UnitOfWork) -> None:
    section(f"Create Match  {rel_badge('N:M')}")
    info("  A match links a tournament, a category, and up to three fighters.")
    info("  Relationship: N:M — Fighter ↔ Match (blue, red, winner roles).")

    # Select tournament
    tournaments = uow.tournaments.get_all()
    tournament = choose_from_list(
        tournaments,
        lambda t: f"{t.name} ({t.location or '?'})",
        "Select Tournament",
    )
    if tournament is None:
        return

    # Select category (optional)
    categories = uow.categories.get_all()
    category = choose_from_list(
        categories,
        lambda c: f"{c.name} | {c.belt_level or '?'} | {c.gender or '?'}",
        "Select Category (optional — 0 to skip)",
    )

    # Select fighters
    fighters = uow.fighters.get_all()
    if not fighters:
        error("No fighters available. Create some fighters first.")
        return

    fighter_label = lambda f: f"{f.first_name} {f.last_name} ({f.belt_level or '?'})"

    console.print(f"\n  {rel_badge('N:M')} [bold]Blue corner fighter[/]")
    blue = choose_from_list(fighters, fighter_label, "Select Blue Fighter (0 = skip)")

    console.print(f"\n  {rel_badge('N:M')} [bold]Red corner fighter[/]")
    red = choose_from_list(fighters, fighter_label, "Select Red Fighter (0 = skip)")

    console.print(f"\n  {rel_badge('N:M')} [bold]Winner[/]")
    winner = choose_from_list(fighters, fighter_label, "Select Winner (0 = skip / TBD)")

    round_num  = ask_int_optional("Round number")
    duration   = ask_float_optional("Duration (seconds)")
    win_method = ask_optional("Win method (e.g. ippon, waza-ari, decision)")
    sched_str  = ask_optional("Scheduled time (YYYY-MM-DD HH:MM)")

    scheduled_time = None
    if sched_str:
        try:
            scheduled_time = datetime.strptime(sched_str, "%Y-%m-%d %H:%M")
        except ValueError:
            console.print("[warning]  Invalid datetime format — skipped.[/]")

    match = Match(
        tournament_id=tournament.tournament_id,
        category_id=category.category_id if category else None,
        blue_fighter_id=blue.fighter_id  if blue   else None,
        red_fighter_id=red.fighter_id    if red    else None,
        winner_id=winner.fighter_id      if winner else None,
        round_number=round_num,
        duration_seconds=duration,
        win_method=win_method,
        scheduled_time=scheduled_time,
    )
    uow.matches.add(match)
    uow.commit()
    success(f"Match created — ID {match.match_id} in tournament '{tournament.name}'.")


def _list_all(uow: UnitOfWork) -> None:
    section("All Matches")
    matches = uow.matches.get_all()
    if not matches:
        empty_table_msg("matches")
    else:
        console.print(f"[info]  Total: {len(matches)}[/]")
        console.print(_match_table(matches))


def _read_by_id(uow: UnitOfWork) -> None:
    section("Get Match by ID")
    mid = ask_int_optional("Match ID")
    if mid is None:
        return

    m = uow.matches.get(mid)
    if m is None:
        error(f"No match with ID {mid}.")
        return

    console.print(_match_table([m], title=f"Match #{mid}"))

    # Show fighters as N:M
    console.print(f"\n  Relationship [bold]N:M[/] — Fighters involved  {rel_badge('N:M')}")
    fighters_table = make_table("Role", "Fighter ID", "Name")
    for role, fid in [("Blue", m.blue_fighter_id), ("Red", m.red_fighter_id), ("Winner", m.winner_id)]:
        if fid:
            f = uow.fighters.get(fid)
            name = f"{f.first_name} {f.last_name}" if f else "?"
        else:
            fid, name = "—", "—"
        fighters_table.add_row(role, str(fid), name)
    console.print(fighters_table)


def _update(uow: UnitOfWork) -> None:
    section("Update Match")
    mid = ask_int_optional("Match ID to update")
    if mid is None:
        return

    m = uow.matches.get(mid)
    if m is None:
        error(f"No match with ID {mid}.")
        return

    info(f"  Match #{mid} — tournament {m.tournament_id}, round {m.round_number}")
    info("  Leave blank to keep current values.")

    # Update winner (N:M — Fighter role changes)
    console.print(f"\n  {rel_badge('N:M')} Update winner fighter ID")
    new_winner = ask_int_optional(f"Winner fighter ID [{m.winner_id or 'none'}]")
    if new_winner is not None:
        m.winner_id = new_winner

    win_method_raw = ask(f"Win method [{m.win_method or ''}]", default=m.win_method or "")
    m.win_method = win_method_raw or None

    dur_raw = ask(f"Duration seconds [{m.duration_seconds or ''}]",
                  default=str(m.duration_seconds or ""))
    try:
        m.duration_seconds = float(dur_raw) if dur_raw else None
    except ValueError:
        pass

    uow.matches.update(m)
    uow.commit()
    success(f"Match #{mid} updated.")


def _delete(uow: UnitOfWork) -> None:
    section("Delete Match")
    mid = ask_int_optional("Match ID to delete")
    if mid is None:
        return

    m = uow.matches.get(mid)
    if m is None:
        error(f"No match with ID {mid}.")
        return

    if not ask_bool(f"Delete match #{mid}?", default=False):
        info("Cancelled.")
        return

    uow.matches.delete(m)
    uow.commit()
    success(f"Match #{mid} deleted.")


# ── Searches ───────────────────────────────────────────────────────────────────

def _filter_by_tournament(uow: UnitOfWork) -> None:
    section("Filter Matches by Tournament")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    results = uow.matches.get_by_tournament(tid)
    if not results:
        info(f"No matches in tournament {tid}.")
    else:
        console.print(_match_table(results, title=f"Tournament #{tid}"))


def _filter_by_fighter(uow: UnitOfWork) -> None:
    section(f"Matches by Fighter  {rel_badge('N:M')}")
    info("  Shows all matches where fighter appears as blue, red or winner.")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    results = uow.matches.get_by_fighter(fid)
    wins    = uow.matches.get_wins_by_fighter(fid)
    if not results:
        info(f"No matches for fighter #{fid}.")
    else:
        console.print(_match_table(results, title=f"All matches — Fighter #{fid}"))
        info(f"  Wins: {len(wins)} / {len(results)}")


def _filter_by_category(uow: UnitOfWork) -> None:
    section("Filter Matches by Category")
    cid = ask_int_optional("Category ID")
    if cid is None:
        return
    results = uow.matches.get_by_category(cid)
    if not results:
        info(f"No matches in category #{cid}.")
    else:
        console.print(_match_table(results, title=f"Category #{cid}"))


def _filter_by_round(uow: UnitOfWork) -> None:
    section("Filter Matches by Round")
    tid = ask_int_optional("Tournament ID")
    rnd = ask_int_optional("Round number")
    if tid is None or rnd is None:
        return
    results = uow.matches.get_by_round(tid, rnd)
    if not results:
        info(f"No matches in tournament {tid}, round {rnd}.")
    else:
        console.print(_match_table(results, title=f"Tournament #{tid} — Round {rnd}"))


def _wins_by_fighter(uow: UnitOfWork) -> None:
    section("Wins by Fighter")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    f = uow.fighters.get(fid)
    name = f"{f.first_name} {f.last_name}" if f else str(fid)
    results = uow.matches.get_wins_by_fighter(fid)
    if not results:
        info(f"No wins found for {name}.")
    else:
        console.print(_match_table(results, title=f"Wins — {name}"))
        info(f"  Total wins: {len(results)}")


# ── Submenu ────────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all matches",                        _list_all),
    ("Get match by ID (+ fighters)",            _read_by_id),
    (f"Create match  [rel_n_m](N:M)[/]",        _create),
    ("Update match",                            _update),
    ("Delete match",                            _delete),
    ("Filter by tournament",                    _filter_by_tournament),
    (f"Matches by fighter  [rel_n_m](N:M)[/]",  _filter_by_fighter),
    ("Filter by category",                      _filter_by_category),
    ("Filter by round",                         _filter_by_round),
    ("Wins by fighter",                         _wins_by_fighter),
]


def matches_menu(session_factory) -> None:
    while True:
        section("Matches")
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
