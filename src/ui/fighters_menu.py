"""
Fighters submenu — CRUD, searches, and relationship management.

Relationships demonstrated:
  - 1:1  Fighter ↔ MedicalRecord
  - 1:N  Fighter → Matches (blue / red / winner)
  - N:M+attrs  Fighter ↔ Category ↔ Tournament (via FighterCategoryRegistration)
"""

from __future__ import annotations

from datetime import datetime

from rich.table import Table

from src.domain.models import Fighter, FighterCategoryRegistration
from src.domain.repositories import UnitOfWork

from .console import console
from .helpers import (
    ask, ask_bool, ask_float_optional, ask_int_optional, ask_optional,
    choose_from_list, empty_table_msg, error, info, make_table,
    pause, rel_badge, section, success,
)


# ── Table renderers ────────────────────────────────────────────────────────────

def _fighter_table(fighters: list[Fighter], title: str = "Fighters") -> Table:
    t = make_table("ID", "First name", "Last name", "Gender",
                   "Belt", "Club", "Country", "Email", title=title)
    for f in fighters:
        t.add_row(
            str(f.fighter_id),
            f.first_name,
            f.last_name,
            f.gender or "—",
            f.belt_level or "—",
            f.club_name or "—",
            f.country or "—",
            f.email or "—",
        )
    return t


def _registration_table(regs: list[FighterCategoryRegistration]) -> Table:
    t = make_table(
        "Fighter ID", "Category ID", "Tournament ID",
        "Weight (kg)", "Approved", "Registered",
        title=f"Registrations  {rel_badge('N:M+attrs')}",
    )
    for r in regs:
        t.add_row(
            str(r.fighter_id),
            str(r.category_id),
            str(r.tournament_id),
            str(r.weight_in_weight_kg or "—"),
            "✓" if r.is_approved else "✗",
            str(r.registration_date)[:19] if r.registration_date else "—",
        )
    return t


# ── CRUD operations ────────────────────────────────────────────────────────────

def _create(uow: UnitOfWork) -> None:
    section("Create Fighter")
    first = ask("First name")
    last  = ask("Last name")
    if not first or not last:
        error("First name and last name are required.")
        return

    gender     = ask_optional("Gender (M/F/Other)")
    belt       = ask_optional("Belt level (e.g. blue, black)")
    club       = ask_optional("Club name")
    country    = ask_optional("Country")
    email      = ask_optional("Email")
    phone      = ask_optional("Phone")
    birth_str  = ask_optional("Birth date (YYYY-MM-DD)")

    birth_date = None
    if birth_str:
        try:
            birth_date = datetime.strptime(birth_str, "%Y-%m-%d")
        except ValueError:
            console.print("[warning]  Invalid date format — birth date skipped.[/]")

    fighter = Fighter(
        first_name=first,
        last_name=last,
        gender=gender,
        belt_level=belt,
        club_name=club,
        country=country,
        email=email,
        phone=phone,
        birth_date=birth_date,
    )
    uow.fighters.add(fighter)
    uow.commit()
    success(f"Fighter created — ID {fighter.fighter_id}: {fighter.first_name} {fighter.last_name}")


def _list_all(uow: UnitOfWork) -> None:
    section("All Fighters")
    fighters = uow.fighters.get_all()
    if not fighters:
        empty_table_msg("fighters")
    else:
        console.print(f"[info]  Total: {len(fighters)}[/]")
        console.print(_fighter_table(fighters))


def _list_paginated(uow: UnitOfWork) -> None:
    section("Fighters — Paginated")
    total = uow.fighters.count()
    if total == 0:
        empty_table_msg("fighters")
        return

    page_size = 5
    page = 1
    while True:
        fighters = uow.fighters.get_paginated(page=page, page_size=page_size)
        if not fighters:
            break
        console.print(f"[info]  Page {page} — showing {len(fighters)} of {total}[/]")
        console.print(_fighter_table(fighters, title=f"Page {page}"))

        total_pages = (total + page_size - 1) // page_size
        if page >= total_pages:
            info("End of list.")
            break

        go_next = ask_bool("Next page?", default=True)
        if not go_next:
            break
        page += 1


def _read_by_id(uow: UnitOfWork) -> None:
    section("Get Fighter by ID")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return

    fighter = uow.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    console.print(_fighter_table([fighter], title=f"Fighter #{fid}"))

    # ── 1:1 MedicalRecord ─────────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]1:1[/] — MedicalRecord  {rel_badge('1:1')}")
    if fighter.medical_record:
        mr = fighter.medical_record
        t = make_table("Blood type", "Doctor", "Conditions", "Notes",
                       title="Medical Record")
        t.add_row(
            mr.blood_type or "—",
            mr.doctor_name or "—",
            mr.conditions or "—",
            mr.notes or "—",
        )
        console.print(t)
    else:
        info("  No medical record attached.")

    # ── N:M+attrs Registrations ────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]N:M with attributes[/]  {rel_badge('N:M+attrs')}")
    regs = uow.registrations.get_by_fighter(fid)
    if regs:
        console.print(_registration_table(regs))
    else:
        info("  No registrations found.")

    # ── 1:N Matches ────────────────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]1:N[/] — Matches  {rel_badge('1:N')}")
    all_matches = uow.matches.get_by_fighter(fid)
    wins        = uow.matches.get_wins_by_fighter(fid)
    info(f"  Total matches: {len(all_matches)}   Wins: {len(wins)}")


def _update(uow: UnitOfWork) -> None:
    section("Update Fighter")
    fid = ask_int_optional("Fighter ID to update")
    if fid is None:
        return

    fighter = uow.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    console.print(f"[info]  Editing: {fighter.first_name} {fighter.last_name}[/]")
    info("  Leave blank to keep the current value.")

    new_first   = ask(f"First name [{fighter.first_name}]", default=fighter.first_name)
    new_last    = ask(f"Last name [{fighter.last_name}]",   default=fighter.last_name)
    new_belt    = ask(f"Belt level [{fighter.belt_level or ''}]",  default=fighter.belt_level or "")
    new_club    = ask(f"Club name [{fighter.club_name or ''}]",    default=fighter.club_name or "")
    new_country = ask(f"Country [{fighter.country or ''}]",        default=fighter.country or "")
    new_email   = ask(f"Email [{fighter.email or ''}]",            default=fighter.email or "")

    fighter.first_name = new_first or fighter.first_name
    fighter.last_name  = new_last  or fighter.last_name
    fighter.belt_level = new_belt  or None
    fighter.club_name  = new_club  or None
    fighter.country    = new_country or None
    fighter.email      = new_email or None

    uow.fighters.update(fighter)
    uow.commit()
    success(f"Fighter #{fid} updated — last_update={fighter.last_update}")


def _delete(uow: UnitOfWork) -> None:
    section("Delete Fighter")
    fid = ask_int_optional("Fighter ID to delete")
    if fid is None:
        return

    fighter = uow.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    confirm = ask_bool(
        f"Delete {fighter.first_name} {fighter.last_name} and ALL their records?",
        default=False,
    )
    if not confirm:
        info("Cancelled.")
        return

    uow.fighters.delete(fighter)
    uow.commit()
    success(f"Fighter #{fid} deleted.")


# ── Search operations ──────────────────────────────────────────────────────────

def _search_by_last_name(uow: UnitOfWork) -> None:
    section("Search by Last Name")
    name = ask("Last name (partial match)")
    results = uow.fighters.get_by_last_name(name)
    if not results:
        info(f"No fighters found matching '{name}'.")
    else:
        console.print(_fighter_table(results, title=f"Results for '{name}'"))


def _search_by_belt(uow: UnitOfWork) -> None:
    section("Filter by Belt Level")
    belt = ask("Belt level (e.g. blue, black, purple)")
    results = uow.fighters.get_by_belt_level(belt)
    if not results:
        info(f"No fighters with belt '{belt}'.")
    else:
        console.print(_fighter_table(results, title=f"Belt: {belt}"))


def _search_by_country(uow: UnitOfWork) -> None:
    section("Filter by Country")
    country = ask("Country")
    results = uow.fighters.get_by_country(country)
    if not results:
        info(f"No fighters from '{country}'.")
    else:
        console.print(_fighter_table(results, title=f"Country: {country}"))


def _search_by_email(uow: UnitOfWork) -> None:
    section("Search by Email")
    email = ask("Email address")
    fighter = uow.fighters.get_by_email(email)
    if fighter is None:
        info(f"No fighter found with email '{email}'.")
    else:
        console.print(_fighter_table([fighter], title="Result"))


# ── 1:1 MedicalRecord management ──────────────────────────────────────────────

def _manage_medical_record(uow: UnitOfWork) -> None:
    section(f"Medical Record  {rel_badge('1:1')}")
    info("  Relationship type: 1:1 — each fighter has at most one medical record.")

    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    fighter = uow.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    info(f"  Fighter: {fighter.first_name} {fighter.last_name}")

    if fighter.medical_record:
        mr = fighter.medical_record
        console.print("[info]  Existing record found — you can update it.[/]")
        mr.blood_type  = ask(f"Blood type [{mr.blood_type or ''}]",    default=mr.blood_type or "")  or None
        mr.doctor_name = ask(f"Doctor [{mr.doctor_name or ''}]",       default=mr.doctor_name or "") or None
        mr.conditions  = ask(f"Conditions [{mr.conditions or ''}]",    default=mr.conditions or "")  or None
        mr.notes       = ask(f"Notes [{mr.notes or ''}]",              default=mr.notes or "")       or None
        uow.fighters.update(fighter)
        uow.commit()
        success("Medical record updated.")
    else:
        info("  No medical record — creating one.")
        blood  = ask_optional("Blood type")
        doctor = ask_optional("Doctor name")
        conds  = ask_optional("Conditions")
        notes  = ask_optional("Notes")
        uow.fighters.add_medical_record(
            fighter_id=fid,
            blood_type=blood,
            doctor_name=doctor,
            conditions=conds,
            notes=notes,
        )
        uow.commit()
        success("Medical record created and attached to fighter.")


# ── N:M+attrs Registration management ─────────────────────────────────────────

def _manage_registration(uow: UnitOfWork) -> None:
    section(f"Register Fighter in Category/Tournament  {rel_badge('N:M+attrs')}")
    info("  Relationship type: N:M with attributes — fighter ↔ category ↔ tournament.")
    info("  The registration row stores extra data: weigh-in weight and approval status.")

    # Pick fighter
    fighters = uow.fighters.get_all()
    fighter = choose_from_list(
        fighters,
        lambda f: f"{f.first_name} {f.last_name} (belt: {f.belt_level or '?'})",
        "Select Fighter",
    )
    if fighter is None:
        return

    # Pick tournament
    tournaments = uow.tournaments.get_all()
    tournament = choose_from_list(
        tournaments,
        lambda t: f"{t.name} — {t.location or '?'} ({t.start_date.date() if t.start_date else '?'})",
        "Select Tournament",
    )
    if tournament is None:
        return

    # Pick category
    categories = uow.categories.get_all()
    category = choose_from_list(
        categories,
        lambda c: f"{c.name} | {c.belt_level or '?'} | {c.gender or '?'} | {c.weight_min_kg}–{c.weight_max_kg} kg",
        "Select Category",
    )
    if category is None:
        return

    # Check if already registered
    existing = uow.registrations.get(
        (fighter.fighter_id, category.category_id, tournament.tournament_id)
    )
    if existing:
        info(f"  Already registered — approved: {existing.is_approved}")
        if ask_bool("Approve this registration now?", default=False):
            uow.fighters.approve_registration(
                fighter.fighter_id, category.category_id, tournament.tournament_id
            )
            uow.commit()
            success("Registration approved.")
        return

    weight = ask_float_optional("Weigh-in weight (kg)")
    reg = FighterCategoryRegistration(
        fighter_id=fighter.fighter_id,
        category_id=category.category_id,
        tournament_id=tournament.tournament_id,
        weight_in_weight_kg=weight,
        is_approved=False,
    )
    uow.registrations.add(reg)
    uow.commit()
    success(
        f"Fighter '{fighter.first_name} {fighter.last_name}' registered in "
        f"'{category.name}' at '{tournament.name}'."
    )


def _approve_registration(uow: UnitOfWork) -> None:
    section(f"Approve Registration  {rel_badge('N:M+attrs')}")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    fighter = uow.fighters.get(fid)
    if fighter is None:
        error(f"No fighter #{fid}.")
        return

    pending = uow.registrations.get_by_fighter(fid)
    pending = [r for r in pending if not r.is_approved]
    if not pending:
        info("No pending registrations for this fighter.")
        return

    console.print(_registration_table(pending))
    cat_id = ask_int_optional("Category ID to approve")
    tour_id = ask_int_optional("Tournament ID to approve")
    if cat_id is None or tour_id is None:
        return

    try:
        uow.fighters.approve_registration(fid, cat_id, tour_id)
        uow.commit()
        success("Registration approved.")
    except ValueError as e:
        error(str(e))


# ── Submenu ────────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all fighters",                       _list_all),
    ("List fighters (paginated)",               _list_paginated),
    ("Get fighter by ID (+ relationships)",     _read_by_id),
    ("Create fighter",                          _create),
    ("Update fighter",                          _update),
    ("Delete fighter",                          _delete),
    ("Search by last name",                     _search_by_last_name),
    ("Filter by belt level",                    _search_by_belt),
    ("Filter by country",                       _search_by_country),
    ("Search by email",                         _search_by_email),
    (f"Manage medical record  [rel_1_1](1:1)[/]",    _manage_medical_record),
    (f"Register in category/tournament  [rel_n_m_attr](N:M+attrs)[/]", _manage_registration),
    (f"Approve registration  [rel_n_m_attr](N:M+attrs)[/]",            _approve_registration),
]


def fighters_menu(session_factory) -> None:
    """Entry point called from the main menu."""
    while True:
        section("Fighters")
        for i, (label, _) in enumerate(_MENU_ITEMS, start=1):
            console.print(f"  [muted]{i:>2}.[/] {label}")
        console.print(f"  [muted] 0.[/] Back to main menu")

        choice = ask_int_optional("Choose an option")
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
