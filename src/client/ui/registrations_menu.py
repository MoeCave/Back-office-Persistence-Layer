"""
client/ui/registrations_menu.py — Registrations submenu adapted for the TCP client.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table

from src.client.gateway import ServerGateway, ServerError
from src.ui.console import console
from src.ui.helpers import (
    ask_bool, ask_float_optional, ask_int_optional,
    choose_from_list, empty_table_msg, error, info, make_table,
    pause, rel_badge, section, success,
)


# ── Table renderer ─────────────────────────────────────────────────────────────

def _reg_table(regs: list[dict[str, Any]], title: str = "") -> Table:
    t = make_table(
        "Fighter ID", "Category ID", "Tournament ID",
        "Weight (kg)", "Approved", "Registered", "Last update",
        title=title or f"Registrations  {rel_badge('N:M+attrs')}",
    )
    for r in regs:
        t.add_row(
            str(r.get("fighter_id")),
            str(r.get("category_id")),
            str(r.get("tournament_id")),
            str(r.get("weight_in_weight_kg")) if r.get("weight_in_weight_kg") else "—",
            "[green]✓[/]" if r.get("is_approved") else "[red]✗[/]",
            (r.get("registration_date") or "—")[:19],
            (r.get("last_update") or "—")[:19],
        )
    return t


# ── Operations ─────────────────────────────────────────────────────────────────

def _list_all(gw: ServerGateway) -> None:
    section(f"All Registrations  {rel_badge('N:M+attrs')}")
    info("  This table is the N:M association between Fighter, Category, and Tournament.")
    info("  Extra attributes: weight_in_weight_kg, is_approved, registration_date.")
    regs = gw.registrations.list_all()
    if not regs:
        empty_table_msg("registrations")
    else:
        console.print(f"[info]  Total: {len(regs)}[/]")
        console.print(_reg_table(regs))


def _list_by_tournament(gw: ServerGateway) -> None:
    section(f"Registrations by Tournament  {rel_badge('N:M+attrs')}")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    regs = gw.registrations.get_by_tournament(tid)
    if not regs:
        info(f"No registrations for tournament {tid}.")
    else:
        console.print(_reg_table(regs, title=f"Tournament #{tid}"))


def _list_by_fighter(gw: ServerGateway) -> None:
    section(f"Registrations by Fighter  {rel_badge('N:M+attrs')}")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    regs = gw.registrations.get_by_fighter(fid)
    if not regs:
        info(f"No registrations for fighter #{fid}.")
    else:
        console.print(_reg_table(regs, title=f"Fighter #{fid}"))


def _pending_approvals(gw: ServerGateway) -> None:
    section(f"Pending Approvals  {rel_badge('N:M+attrs')}")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    regs = gw.registrations.get_pending_approvals(tid)
    if not regs:
        info(f"No pending approvals in tournament #{tid}.")
    else:
        console.print(_reg_table(regs, title=f"Pending — Tournament #{tid}"))


def _create(gw: ServerGateway) -> None:
    section(f"Create Registration  {rel_badge('N:M+attrs')}")
    info("  You are creating an N:M link with attributes between:")
    info("  Fighter ↔ Category ↔ Tournament")

    fighters = gw.fighters.list_all()
    fighter = choose_from_list(
        fighters,
        lambda f: f"{f['first_name']} {f['last_name']} (belt: {f.get('belt_level') or '?'})",
        "Select Fighter",
    )
    if fighter is None:
        return

    categories = gw.categories.list_all()
    category = choose_from_list(
        categories,
        lambda c: (
            f"{c['name']} | {c.get('belt_level') or '?'} | "
            f"{c.get('gender') or '?'} | "
            f"{c.get('weight_min_kg')}–{c.get('weight_max_kg')} kg"
        ),
        "Select Category",
    )
    if category is None:
        return

    tournaments = gw.tournaments.list_all()
    tournament = choose_from_list(
        tournaments,
        lambda t: f"{t['name']} ({t.get('location') or '?'})",
        "Select Tournament",
    )
    if tournament is None:
        return

    existing = gw.registrations.get(
        (fighter["fighter_id"], category["category_id"], tournament["tournament_id"])
    )
    if existing:
        error("This registration already exists.")
        console.print(_reg_table([existing]))
        return

    weight = ask_float_optional("Weigh-in weight (kg)  ← extra N:M attribute")
    approved = ask_bool("Pre-approve?  ← extra N:M attribute", default=False)

    try:
        gw.registrations.add({
            "fighter_id": fighter["fighter_id"],
            "category_id": category["category_id"],
            "tournament_id": tournament["tournament_id"],
            "weight_in_weight_kg": weight,
            "is_approved": approved,
        })
        success(
            f"Registered '{fighter['first_name']} {fighter['last_name']}' "
            f"in '{category['name']}' @ '{tournament['name']}'."
        )
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _approve(gw: ServerGateway) -> None:
    section(f"Approve Registration  {rel_badge('N:M+attrs')}")
    fid = ask_int_optional("Fighter ID")
    cid = ask_int_optional("Category ID")
    tid = ask_int_optional("Tournament ID")
    if None in (fid, cid, tid):
        return

    reg = gw.registrations.get((fid, cid, tid))
    if reg is None:
        error("Registration not found.")
        return
    if reg.get("is_approved"):
        info("Already approved.")
        return

    try:
        gw.fighters.approve_registration(fid, cid, tid)
        success("Registration approved.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _update(gw: ServerGateway) -> None:
    section(f"Update Registration attributes  {rel_badge('N:M+attrs')}")
    info("  Update the extra attributes on the association row.")
    fid = ask_int_optional("Fighter ID")
    cid = ask_int_optional("Category ID")
    tid = ask_int_optional("Tournament ID")
    if None in (fid, cid, tid):
        return

    reg = gw.registrations.get((fid, cid, tid))
    if reg is None:
        error("Registration not found.")
        return

    console.print(_reg_table([reg]))

    new_weight = ask_float_optional(
        f"New weigh-in weight (kg) [{reg.get('weight_in_weight_kg') or 'none'}]"
    )
    new_approved = ask_bool(
        f"Approved? [{reg.get('is_approved')}]",
        default=bool(reg.get("is_approved")),
    )

    try:
        gw.registrations.update({
            "fighter_id": fid,
            "category_id": cid,
            "tournament_id": tid,
            "weight_in_weight_kg": new_weight,
            "is_approved": new_approved,
        })
        success("Registration updated.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _delete(gw: ServerGateway) -> None:
    section(f"Delete Registration  {rel_badge('N:M+attrs')}")
    fid = ask_int_optional("Fighter ID")
    cid = ask_int_optional("Category ID")
    tid = ask_int_optional("Tournament ID")
    if None in (fid, cid, tid):
        return

    reg = gw.registrations.get((fid, cid, tid))
    if reg is None:
        error("Registration not found.")
        return

    console.print(_reg_table([reg]))
    if not ask_bool("Delete this registration?", default=False):
        info("Cancelled.")
        return

    try:
        gw.registrations.delete({
            "fighter_id": fid,
            "category_id": cid,
            "tournament_id": tid,
        })
        success("Registration deleted.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


# ── Submenu ────────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    (f"List all registrations  [rel_n_m_attr](N:M+attrs)[/]",         _list_all),
    ("List by tournament",                                               _list_by_tournament),
    ("List by fighter",                                                  _list_by_fighter),
    ("Pending approvals by tournament",                                  _pending_approvals),
    (f"Create registration  [rel_n_m_attr](N:M+attrs)[/]",             _create),
    (f"Update registration attributes  [rel_n_m_attr](N:M+attrs)[/]",  _update),
    (f"Approve registration  [rel_n_m_attr](N:M+attrs)[/]",            _approve),
    ("Delete registration",                                              _delete),
]


def registrations_menu(gw: ServerGateway) -> None:
    while True:
        section(f"Registrations  {rel_badge('N:M+attrs')}")
        info("  This submenu manages the Fighter ↔ Category ↔ Tournament association table.")
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
            handler(gw)
        except Exception as exc:
            error(f"Unexpected error: {exc}")

        pause()
