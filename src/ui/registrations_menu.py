"""
Registrations submenu — manages the N:M+attrs association table.

FighterCategoryRegistration is the explicit association object that
links Fighter ↔ Category ↔ Tournament and adds:
  - weight_in_weight_kg  (extra attribute)
  - is_approved          (extra attribute)
  - registration_date    (extra attribute)

This menu exists to demonstrate the N:M with attributes pattern clearly.
"""

from __future__ import annotations

from rich.table import Table

from src.domain.models import FighterCategoryRegistration
from src.domain.repositories import UnitOfWork

from .console import console
from .helpers import (
    ask_bool, ask_float_optional, ask_int_optional,
    choose_from_list, empty_table_msg, error, info, make_table,
    pause, rel_badge, section, success,
)


# ── Table renderer ─────────────────────────────────────────────────────────────

def _reg_table(regs: list[FighterCategoryRegistration], title: str = "") -> Table:
    t = make_table(
        "Fighter ID", "Category ID", "Tournament ID",
        "Weight (kg)", "Approved", "Registered",
        "Last update",
        title=title or f"Registrations  {rel_badge('N:M+attrs')}",
    )
    for r in regs:
        t.add_row(
            str(r.fighter_id),
            str(r.category_id),
            str(r.tournament_id),
            str(r.weight_in_weight_kg) if r.weight_in_weight_kg else "—",
            "[green]✓[/]" if r.is_approved else "[red]✗[/]",
            str(r.registration_date)[:19] if r.registration_date else "—",
            str(r.last_update)[:19]       if r.last_update        else "—",
        )
    return t


# ── Operations ─────────────────────────────────────────────────────────────────

def _list_all(uow: UnitOfWork) -> None:
    section(f"All Registrations  {rel_badge('N:M+attrs')}")
    info("  This table is the N:M association between Fighter, Category, and Tournament.")
    info("  Extra attributes: weight_in_weight_kg, is_approved, registration_date.")
    regs = uow.registrations.get_all()
    if not regs:
        empty_table_msg("registrations")
    else:
        console.print(f"[info]  Total: {len(regs)}[/]")
        console.print(_reg_table(regs))


def _list_by_tournament(uow: UnitOfWork) -> None:
    section(f"Registrations by Tournament  {rel_badge('N:M+attrs')}")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    regs = uow.registrations.get_by_tournament(tid)
    if not regs:
        info(f"No registrations for tournament {tid}.")
    else:
        console.print(_reg_table(regs, title=f"Tournament #{tid}"))


def _list_by_fighter(uow: UnitOfWork) -> None:
    section(f"Registrations by Fighter  {rel_badge('N:M+attrs')}")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    regs = uow.registrations.get_by_fighter(fid)
    if not regs:
        info(f"No registrations for fighter #{fid}.")
    else:
        console.print(_reg_table(regs, title=f"Fighter #{fid}"))


def _pending_approvals(uow: UnitOfWork) -> None:
    section(f"Pending Approvals  {rel_badge('N:M+attrs')}")
    tid = ask_int_optional("Tournament ID")
    if tid is None:
        return
    regs = uow.registrations.get_pending_approvals(tid)
    if not regs:
        info(f"No pending approvals in tournament #{tid}.")
    else:
        console.print(_reg_table(regs, title=f"Pending — Tournament #{tid}"))


def _create(uow: UnitOfWork) -> None:
    section(f"Create Registration  {rel_badge('N:M+attrs')}")
    info("  You are creating an N:M link with attributes between:")
    info("  Fighter ↔ Category ↔ Tournament")

    fighters = uow.fighters.get_all()
    fighter = choose_from_list(
        fighters,
        lambda f: f"{f.first_name} {f.last_name} (belt: {f.belt_level or '?'})",
        "Select Fighter",
    )
    if fighter is None:
        return

    categories = uow.categories.get_all()
    category = choose_from_list(
        categories,
        lambda c: f"{c.name} | {c.belt_level or '?'} | {c.gender or '?'} | {c.weight_min_kg}–{c.weight_max_kg} kg",
        "Select Category",
    )
    if category is None:
        return

    tournaments = uow.tournaments.get_all()
    tournament = choose_from_list(
        tournaments,
        lambda t: f"{t.name} ({t.location or '?'})",
        "Select Tournament",
    )
    if tournament is None:
        return

    existing = uow.registrations.get(
        (fighter.fighter_id, category.category_id, tournament.tournament_id)
    )
    if existing:
        error("This registration already exists.")
        console.print(_reg_table([existing]))
        return

    weight = ask_float_optional("Weigh-in weight (kg)  ← extra N:M attribute")
    approved = ask_bool("Pre-approve?  ← extra N:M attribute", default=False)

    reg = FighterCategoryRegistration(
        fighter_id=fighter.fighter_id,
        category_id=category.category_id,
        tournament_id=tournament.tournament_id,
        weight_in_weight_kg=weight,
        is_approved=approved,
    )
    uow.registrations.add(reg)
    uow.commit()
    success(
        f"Registered '{fighter.first_name} {fighter.last_name}' "
        f"in '{category.name}' @ '{tournament.name}'."
    )


def _approve(uow: UnitOfWork) -> None:
    section(f"Approve Registration  {rel_badge('N:M+attrs')}")
    fid  = ask_int_optional("Fighter ID")
    cid  = ask_int_optional("Category ID")
    tid  = ask_int_optional("Tournament ID")
    if None in (fid, cid, tid):
        return

    reg = uow.registrations.get((fid, cid, tid))
    if reg is None:
        error("Registration not found.")
        return
    if reg.is_approved:
        info("Already approved.")
        return

    try:
        uow.fighters.approve_registration(fid, cid, tid)
        uow.commit()
        success("Registration approved.")
    except ValueError as e:
        error(str(e))


def _update(uow: UnitOfWork) -> None:
    section(f"Update Registration attributes  {rel_badge('N:M+attrs')}")
    info("  Update the extra attributes on the association row.")
    fid  = ask_int_optional("Fighter ID")
    cid  = ask_int_optional("Category ID")
    tid  = ask_int_optional("Tournament ID")
    if None in (fid, cid, tid):
        return

    reg = uow.registrations.get((fid, cid, tid))
    if reg is None:
        error("Registration not found.")
        return

    console.print(_reg_table([reg]))

    new_weight = ask_float_optional(
        f"New weigh-in weight (kg) [{reg.weight_in_weight_kg or 'none'}]"
    )
    if new_weight is not None:
        reg.weight_in_weight_kg = new_weight

    reg.is_approved = ask_bool(
        f"Approved? [{reg.is_approved}]", default=reg.is_approved
    )

    uow.registrations.update(reg)
    uow.commit()
    success("Registration updated.")


def _delete(uow: UnitOfWork) -> None:
    section(f"Delete Registration  {rel_badge('N:M+attrs')}")
    fid  = ask_int_optional("Fighter ID")
    cid  = ask_int_optional("Category ID")
    tid  = ask_int_optional("Tournament ID")
    if None in (fid, cid, tid):
        return

    reg = uow.registrations.get((fid, cid, tid))
    if reg is None:
        error("Registration not found.")
        return

    console.print(_reg_table([reg]))
    if not ask_bool("Delete this registration?", default=False):
        info("Cancelled.")
        return

    uow.registrations.delete(reg)
    uow.commit()
    success("Registration deleted.")


# ── Submenu ────────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    (f"List all registrations  [rel_n_m_attr](N:M+attrs)[/]",     _list_all),
    ("List by tournament",                                          _list_by_tournament),
    ("List by fighter",                                             _list_by_fighter),
    ("Pending approvals by tournament",                             _pending_approvals),
    (f"Create registration  [rel_n_m_attr](N:M+attrs)[/]",         _create),
    (f"Update registration attributes  [rel_n_m_attr](N:M+attrs)[/]", _update),
    (f"Approve registration  [rel_n_m_attr](N:M+attrs)[/]",        _approve),
    ("Delete registration",                                         _delete),
]


def registrations_menu(session_factory) -> None:
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
            with UnitOfWork(session_factory=session_factory) as uow:
                handler(uow)
        except Exception as exc:
            error(f"Unexpected error: {exc}")

        pause()
