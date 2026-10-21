"""
client/ui/matches_menu.py — Matches submenu adapted for the TCP client.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table

from src.client.gateway import ServerGateway, ServerError
from src.client.ui.console import console
from src.client.ui.helpers import fighter_label, run_handler
from src.client.ui.helpers import (
    ask,
    ask_bool,
    ask_float_optional,
    ask_int_optional,
    ask_optional,
    choose_from_list,
    empty_table_msg,
    error,
    info,
    make_table,
    pause,
    rel_badge,
    section,
    success,
)

# ── Table renderer ───────────────────────────────────────────────────────────


def _match_table(
    matches: list[dict[str, Any]], title: str = "Matches"
) -> Table:
    t = make_table(
        "ID",
        "Tournament",
        "Category",
        "Round",
        "Blue fighter",
        "Red fighter",
        "Winner",
        "Method",
        "Duration (s)",
        "Scheduled",
        title=title,
    )
    for m in matches:
        t.add_row(
            str(m.get("match_id", "—")),
            str(m.get("tournament_id", "—")),
            str(m.get("category_id") or "—"),
            str(m.get("round_number") or "—"),
            str(m.get("blue_fighter_id") or "—"),
            str(m.get("red_fighter_id") or "—"),
            str(m.get("winner_id") or "—"),
            m.get("win_method") or "—",
            str(m.get("duration_seconds") or "—"),
            (m.get("scheduled_time") or "—")[:16],
        )
    return t


# ── CRUD ─────────────────────────────────────────────────────────────────────


def _create(gw: ServerGateway) -> None:
    section(f"Create Match  {rel_badge('N:M')}")
    info("  A match links a tournament, a category, and up to three fighters.")
    info("  Relationship: N:M — Fighter ↔ Match (blue, red, winner roles).")

    tournaments = gw.tournaments.list_all()
    tournament = choose_from_list(
        tournaments,
        lambda t: f"{t['name']} ({t.get('location') or '?'})",
        "Select Tournament",
    )
    if tournament is None:
        return

    categories = gw.categories.list_all()
    category = choose_from_list(
        categories,
        lambda c: (
            f"{c['name']} | {c.get('belt_level') or '?'} | "
            f"{c.get('gender') or '?'}"
        ),
        "Select Category (optional — 0 to skip)",
    )

    fighters = gw.fighters.list_all()
    if not fighters:
        error("No fighters available. Create some fighters first.")
        return

    console.print(f"\n  {rel_badge('N:M')} [bold]Blue corner fighter[/]")
    blue = choose_from_list(
        fighters, fighter_label, "Select Blue Fighter (0 = skip)"
    )

    console.print(f"\n  {rel_badge('N:M')} [bold]Red corner fighter[/]")
    red = choose_from_list(
        fighters, fighter_label, "Select Red Fighter (0 = skip)"
    )

    console.print(f"\n  {rel_badge('N:M')} [bold]Winner[/]")
    winner = choose_from_list(
        fighters, fighter_label, "Select Winner (0 = skip / TBD)"
    )

    round_num = ask_int_optional("Round number")
    duration = ask_float_optional("Duration (seconds)")
    win_method = ask_optional("Win method (e.g. ippon, waza-ari, decision)")
    sched_str = ask_optional("Scheduled time (YYYY-MM-DD HH:MM)")

    try:
        match = gw.matches.create(
            tournament_id=tournament["tournament_id"],
            category_id=category["category_id"] if category else None,
            blue_fighter_id=blue["fighter_id"] if blue else None,
            red_fighter_id=red["fighter_id"] if red else None,
            winner_id=winner["fighter_id"] if winner else None,
            round_number=round_num,
            duration_seconds=duration,
            win_method=win_method,
            scheduled_time=sched_str,
        )
        success(
            f"Match created — ID {match['match_id']} in tournament "
            f"'{tournament['name']}'."
        )
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _list_all(gw: ServerGateway) -> None:
    section("All Matches")
    matches = gw.matches.list_all()
    if not matches:
        empty_table_msg("matches")
    else:
        console.print(f"[info]  Total: {len(matches)}[/]")
        console.print(_match_table(matches))


def _read_by_id(gw: ServerGateway) -> None:
    section("Get Match by ID")
    mid = ask_int_optional("Match ID")
    if mid is None:
        return

    m = gw.matches.get(mid)
    if m is None:
        error(f"No match with ID {mid}.")
        return

    console.print(_match_table([m], title=f"Match #{mid}"))

    console.print(
        "\n  Relationship [bold]N:M[/] — Fighters involved  "
        f"{rel_badge('N:M')}"
    )
    fighters_table = make_table("Role", "Fighter ID", "Name")
    fighters_info = m.get("fighters_info", {})
    for role in ("blue", "red", "winner"):
        fid_key = f"{role}_fighter_id" if role != "winner" else "winner_id"
        fid = m.get(fid_key)
        name = fighters_info.get(role) or "—"
        fighters_table.add_row(role.capitalize(), str(fid or "—"), name)
    console.print(fighters_table)


def _update(gw: ServerGateway) -> None:
    section("Update Match")
    mid = ask_int_optional("Match ID to update")
    if mid is None:
        return

    m = gw.matches.get(mid)
    if m is None:
        error(f"No match with ID {mid}.")
        return

    info(
        f"  Match #{mid} — tournament {m.get('tournament_id')}, "
        f"round {m.get('round_number')}"
    )
    info("  Leave blank to keep current values.")

    console.print(f"\n  {rel_badge('N:M')} Update winner fighter ID")
    new_winner = ask_int_optional(
        f"Winner fighter ID [{m.get('winner_id') or 'none'}]"
    )

    win_method_raw = ask(
        f"Win method [{m.get('win_method') or ''}]",
        default=m.get("win_method") or "",
    )
    dur_raw = ask(
        f"Duration seconds [{m.get('duration_seconds') or ''}]",
        default=str(m.get("duration_seconds") or ""),
    )
    try:
        new_dur = float(dur_raw) if dur_raw else None
    except ValueError:
        new_dur = None

    try:
        gw.matches.update(
            mid,
            winner_id=new_winner,
            win_method=win_method_raw or None,
            duration_seconds=new_dur,
        )
        success(f"Match #{mid} updated.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _delete(gw: ServerGateway) -> None:
    section("Delete Match")
    mid = ask_int_optional("Match ID to delete")
    if mid is None:
        return

    m = gw.matches.get(mid)
    if m is None:
        error(f"No match with ID {mid}.")
        return

    if not ask_bool(f"Delete match #{mid}?", default=False):
        info("Cancelled.")
        return

    try:
        gw.matches.delete(mid)
        success(f"Match #{mid} deleted.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


# ── Searches ─────────────────────────────────────────────────────────────────


def _filter_by_tournament(gw: ServerGateway) -> None:
    section("Filter Matches by Tournament")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    results = gw.matches.get_by_tournament(tid)
    if not results:
        info(f"No matches in tournament {tid}.")
    else:
        console.print(_match_table(results, title=f"Tournament #{tid}"))


def _filter_by_fighter(gw: ServerGateway) -> None:
    section(f"Matches by Fighter  {rel_badge('N:M')}")
    info("  Shows all matches where fighter appears as blue, red or winner.")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    result = gw.matches.get_by_fighter(fid)
    matches = result.get("matches", [])
    wins = result.get("total_wins", 0)
    if not matches:
        info(f"No matches for fighter #{fid}.")
    else:
        console.print(
            _match_table(matches, title=f"All matches — Fighter #{fid}")
        )
        info(f"  Wins: {wins} / {len(matches)}")


def _filter_by_category(gw: ServerGateway) -> None:
    section("Filter Matches by Category")
    cid = ask_int_optional("Category ID")
    if cid is None:
        return
    results = gw.matches.get_by_category(cid)
    if not results:
        info(f"No matches in category #{cid}.")
    else:
        console.print(_match_table(results, title=f"Category #{cid}"))


def _filter_by_round(gw: ServerGateway) -> None:
    section("Filter Matches by Round")
    tid = ask_int_optional("Tournament ID")
    rnd = ask_int_optional("Round number")
    if tid is None or rnd is None:
        return
    results = gw.matches.get_by_round(tid, rnd)
    if not results:
        info(f"No matches in tournament {tid}, round {rnd}.")
    else:
        console.print(
            _match_table(results, title=f"Tournament #{tid} — Round {rnd}")
        )


def _wins_by_fighter(gw: ServerGateway) -> None:
    section("Wins by Fighter")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    results = gw.matches.get_wins_by_fighter(fid)
    if not results:
        info(f"No wins found for fighter #{fid}.")
    else:
        console.print(_match_table(results, title=f"Wins — Fighter #{fid}"))
        info(f"  Total wins: {len(results)}")


# ── Submenu ──────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all matches", _list_all),
    ("Get match by ID (+ fighters)", _read_by_id),
    ("Create match  [rel_n_m](N:M)[/]", _create),
    ("Update match", _update),
    ("Delete match", _delete),
    ("Filter by tournament", _filter_by_tournament),
    ("Matches by fighter  [rel_n_m](N:M)[/]", _filter_by_fighter),
    ("Filter by category", _filter_by_category),
    ("Filter by round", _filter_by_round),
    ("Wins by fighter", _wins_by_fighter),
]


def matches_menu(gw: ServerGateway) -> None:
    while True:
        section("Matches")
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
