"""
client/ui/fighters_menu.py — Fighters submenu adapted for the TCP client.

Replaces direct UnitOfWork/ORM access with ServerGateway calls.
Data comes back as plain dicts instead of SQLAlchemy model instances.
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

# ── Table renderers ──────────────────────────────────────────────────────────


def _fighter_table(
    fighters: list[dict[str, Any]], title: str = "Fighters"
) -> Table:
    t = make_table(
        "ID",
        "First name",
        "Last name",
        "Gender",
        "Belt",
        "Club",
        "Country",
        "Email",
        title=title,
    )
    for f in fighters:
        t.add_row(
            str(f.get("fighter_id", "—")),
            f.get("first_name", "—"),
            f.get("last_name", "—"),
            f.get("gender") or "—",
            f.get("belt_level") or "—",
            f.get("club_name") or "—",
            f.get("country") or "—",
            f.get("email") or "—",
        )
    return t


def _registration_table(regs: list[dict[str, Any]]) -> Table:
    t = make_table(
        "Fighter ID",
        "Category ID",
        "Tournament ID",
        "Weight (kg)",
        "Approved",
        "Registered",
        title=f"Registrations  {rel_badge('N:M+attrs')}",
    )
    for r in regs:
        t.add_row(
            str(r.get("fighter_id")),
            str(r.get("category_id")),
            str(r.get("tournament_id")),
            str(r.get("weight_in_weight_kg") or "—"),
            "✓" if r.get("is_approved") else "✗",
            (r.get("registration_date") or "—")[:19],
        )
    return t


# ── CRUD operations ──────────────────────────────────────────────────────────


def _create(gw: ServerGateway) -> None:
    section("Create Fighter")
    first = ask("First name")
    last = ask("Last name")
    if not first or not last:
        error("First name and last name are required.")
        return

    gender = ask_optional("Gender (M/F/Other)")
    belt = ask_optional("Belt level (e.g. blue, black)")
    club = ask_optional("Club name")
    country = ask_optional("Country")
    email = ask_optional("Email")
    phone = ask_optional("Phone")
    birth_str = ask_optional("Birth date (YYYY-MM-DD)")

    try:
        fighter = gw.fighters.create(
            first_name=first,
            last_name=last,
            gender=gender,
            belt_level=belt,
            club_name=club,
            country=country,
            email=email,
            phone=phone,
            birth_date=birth_str,
        )
        success(
            f"Fighter created — ID {fighter['fighter_id']}: "
            f"{fighter['first_name']} {fighter['last_name']}"
        )
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _list_all(gw: ServerGateway) -> None:
    section("All Fighters")
    fighters = gw.fighters.list_all()
    if not fighters:
        empty_table_msg("fighters")
    else:
        console.print(f"[info]  Total: {len(fighters)}[/]")
        console.print(_fighter_table(fighters))


def _list_paginated(gw: ServerGateway) -> None:
    section("Fighters — Paginated")
    total = gw.fighters.count()
    if total == 0:
        empty_table_msg("fighters")
        return

    page_size = 5
    page = 1
    while True:
        fighters = gw.fighters.get_paginated(page=page, page_size=page_size)
        if not fighters:
            break
        console.print(
            f"[info]  Page {page} — showing {len(fighters)} of {total}[/]"
        )
        console.print(_fighter_table(fighters, title=f"Page {page}"))

        total_pages = (total + page_size - 1) // page_size
        if page >= total_pages:
            info("End of list.")
            break

        if not ask_bool("Next page?", default=True):
            break
        page += 1


def _read_by_id(gw: ServerGateway) -> None:
    section("Get Fighter by ID")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return

    fighter = gw.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    console.print(_fighter_table([fighter], title=f"Fighter #{fid}"))

    # ── 1:1 MedicalRecord ────────────────────────────────────────────────────
    console.print(
        f"\n  Relationship [bold]1:1[/] — MedicalRecord  {rel_badge('1:1')}"
    )
    mr = fighter.get("medical_record")
    if mr:
        t = make_table(
            "Blood type",
            "Doctor",
            "Conditions",
            "Notes",
            title="Medical Record",
        )
        t.add_row(
            mr.get("blood_type") or "—",
            mr.get("doctor_name") or "—",
            mr.get("conditions") or "—",
            mr.get("notes") or "—",
        )
        console.print(t)
    else:
        info("  No medical record attached.")

    # ── N:M+attrs Registrations ──────────────────────────────────────────────
    console.print(
        "\n  Relationship [bold]N:M with attributes[/]  "
        f"{rel_badge('N:M+attrs')}"
    )
    regs = fighter.get("registrations", [])
    if regs:
        console.print(_registration_table(regs))
    else:
        info("  No registrations found.")

    # ── 1:N Matches ──────────────────────────────────────────────────────────
    console.print(
        f"\n  Relationship [bold]1:N[/] — Matches  {rel_badge('1:N')}"
    )
    info(
        f"  Total matches: {fighter.get('total_matches', 0)}   "
        f"Wins: {fighter.get('total_wins', 0)}"
    )


def _update(gw: ServerGateway) -> None:
    section("Update Fighter")
    fid = ask_int_optional("Fighter ID to update")
    if fid is None:
        return

    fighter = gw.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    console.print(
        f"[info]  Editing: {fighter['first_name']} {fighter['last_name']}[/]"
    )
    info("  Leave blank to keep the current value.")

    new_first = ask(
        f"First name [{fighter['first_name']}]", default=fighter["first_name"]
    )
    new_last = ask(
        f"Last name [{fighter['last_name']}]", default=fighter["last_name"]
    )
    new_belt = ask(
        f"Belt level [{fighter.get('belt_level') or ''}]",
        default=fighter.get("belt_level") or "",
    )
    new_club = ask(
        f"Club name [{fighter.get('club_name') or ''}]",
        default=fighter.get("club_name") or "",
    )
    new_country = ask(
        f"Country [{fighter.get('country') or ''}]",
        default=fighter.get("country") or "",
    )
    new_email = ask(
        f"Email [{fighter.get('email') or ''}]",
        default=fighter.get("email") or "",
    )

    try:
        gw.fighters.update(
            fid,
            first_name=new_first or fighter["first_name"],
            last_name=new_last or fighter["last_name"],
            belt_level=new_belt or None,
            club_name=new_club or None,
            country=new_country or None,
            email=new_email or None,
        )
        success(f"Fighter #{fid} updated.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _delete(gw: ServerGateway) -> None:
    section("Delete Fighter")
    fid = ask_int_optional("Fighter ID to delete")
    if fid is None:
        return

    fighter = gw.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    if not ask_bool(
        f"Delete {fighter['first_name']} {fighter['last_name']} "
        "and ALL their records?",
        default=False,
    ):
        info("Cancelled.")
        return

    try:
        gw.fighters.delete(fid)
        success(f"Fighter #{fid} deleted.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


# ── Search operations ────────────────────────────────────────────────────────


def _search_by_last_name(gw: ServerGateway) -> None:
    section("Search by Last Name")
    name = ask("Last name (partial match)")
    results = gw.fighters.get_by_last_name(name)
    if not results:
        info(f"No fighters found matching '{name}'.")
    else:
        console.print(_fighter_table(results, title=f"Results for '{name}'"))


def _search_by_belt(gw: ServerGateway) -> None:
    section("Filter by Belt Level")
    belt = ask("Belt level (e.g. blue, black, purple)")
    results = gw.fighters.get_by_belt_level(belt)
    if not results:
        info(f"No fighters with belt '{belt}'.")
    else:
        console.print(_fighter_table(results, title=f"Belt: {belt}"))


def _search_by_country(gw: ServerGateway) -> None:
    section("Filter by Country")
    country = ask("Country")
    results = gw.fighters.get_by_country(country)
    if not results:
        info(f"No fighters from '{country}'.")
    else:
        console.print(_fighter_table(results, title=f"Country: {country}"))


def _search_by_email(gw: ServerGateway) -> None:
    section("Search by Email")
    email = ask("Email address")
    fighter = gw.fighters.get_by_email(email)
    if fighter is None:
        info(f"No fighter found with email '{email}'.")
    else:
        console.print(_fighter_table([fighter], title="Result"))


# ── 1:1 MedicalRecord management ─────────────────────────────────────────────


def _manage_medical_record(gw: ServerGateway) -> None:
    section(f"Medical Record  {rel_badge('1:1')}")
    info(
        "  Relationship type: 1:1 — each fighter has at most one "
        "medical record."
    )

    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    fighter = gw.fighters.get(fid)
    if fighter is None:
        error(f"No fighter found with ID {fid}.")
        return

    info(f"  Fighter: {fighter['first_name']} {fighter['last_name']}")
    mr = fighter.get("medical_record")

    if mr:
        console.print("[info]  Existing record found — you can update it.[/]")
        blood = (
            ask(
                f"Blood type [{mr.get('blood_type') or ''}]",
                default=mr.get("blood_type") or "",
            )
            or None
        )
        doctor = (
            ask(
                f"Doctor [{mr.get('doctor_name') or ''}]",
                default=mr.get("doctor_name") or "",
            )
            or None
        )
        conds = (
            ask(
                f"Conditions [{mr.get('conditions') or ''}]",
                default=mr.get("conditions") or "",
            )
            or None
        )
        notes = (
            ask(
                f"Notes [{mr.get('notes') or ''}]",
                default=mr.get("notes") or "",
            )
            or None
        )
    else:
        info("  No medical record — creating one.")
        blood = ask_optional("Blood type")
        doctor = ask_optional("Doctor name")
        conds = ask_optional("Conditions")
        notes = ask_optional("Notes")

    try:
        gw.fighters.upsert_medical_record(
            fid,
            blood_type=blood,
            doctor_name=doctor,
            conditions=conds,
            notes=notes,
        )
        success("Medical record saved.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


# ── N:M+attrs Registration management ────────────────────────────────────────


def _manage_registration(gw: ServerGateway) -> None:
    section(
        f"Register Fighter in Category/Tournament  {rel_badge('N:M+attrs')}"
    )
    info(
        "  Relationship type: N:M with attributes — "
        "fighter ↔ category ↔ tournament."
    )

    fighters = gw.fighters.list_all()
    fighter = choose_from_list(
        fighters,
        fighter_label,
        "Select Fighter",
    )
    if fighter is None:
        return

    tournaments = gw.tournaments.list_all()
    tournament = choose_from_list(
        tournaments,
        lambda t: (
            f"{t['name']} — {t.get('location') or '?'} "
            f"({(t.get('start_date') or '?')[:10]})"
        ),
        "Select Tournament",
    )
    if tournament is None:
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

    existing = gw.registrations.get(
        (
            fighter["fighter_id"],
            category["category_id"],
            tournament["tournament_id"],
        )
    )
    if existing:
        info(f"  Already registered — approved: {existing.get('is_approved')}")
        if ask_bool("Approve this registration now?", default=False):
            try:
                gw.fighters.approve_registration(
                    fighter["fighter_id"],
                    category["category_id"],
                    tournament["tournament_id"],
                )
                success("Registration approved.")
            except (ServerError, ValueError) as exc:
                error(str(exc))
        return

    weight = ask_float_optional("Weigh-in weight (kg)")
    try:
        gw.registrations.add(
            {
                "fighter_id": fighter["fighter_id"],
                "category_id": category["category_id"],
                "tournament_id": tournament["tournament_id"],
                "weight_in_weight_kg": weight,
                "is_approved": False,
            }
        )
        success(
            f"Fighter '{fighter['first_name']} {fighter['last_name']}' "
            "registered in "
            f"'{category['name']}' at '{tournament['name']}'."
        )
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _approve_registration(gw: ServerGateway) -> None:
    section(f"Approve Registration  {rel_badge('N:M+attrs')}")
    fid = ask_int_optional("Fighter ID")
    if fid is None:
        return
    fighter = gw.fighters.get(fid)
    if fighter is None:
        error(f"No fighter #{fid}.")
        return

    pending_all = gw.registrations.get_by_fighter(fid)
    pending = [r for r in pending_all if not r.get("is_approved")]
    if not pending:
        info("No pending registrations for this fighter.")
        return

    console.print(_registration_table(pending))
    cat_id = ask_int_optional("Category ID to approve")
    tour_id = ask_int_optional("Tournament ID to approve")
    if cat_id is None or tour_id is None:
        return

    try:
        gw.fighters.approve_registration(fid, cat_id, tour_id)
        success("Registration approved.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


# ── Submenu ──────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all fighters", _list_all),
    ("List fighters (paginated)", _list_paginated),
    ("Get fighter by ID (+ relationships)", _read_by_id),
    ("Create fighter", _create),
    ("Update fighter", _update),
    ("Delete fighter", _delete),
    ("Search by last name", _search_by_last_name),
    ("Filter by belt level", _search_by_belt),
    ("Filter by country", _search_by_country),
    ("Search by email", _search_by_email),
    ("Manage medical record  [rel_1_1](1:1)[/]", _manage_medical_record),
    (
        "Register in category/tournament  [rel_n_m_attr](N:M+attrs)[/]",
        _manage_registration,
    ),
    (
        "Approve registration  [rel_n_m_attr](N:M+attrs)[/]",
        _approve_registration,
    ),
]


def fighters_menu(gw: ServerGateway) -> None:
    """Entry point called from the main menu."""
    while True:
        section("Fighters")
        for i, (label, _) in enumerate(_MENU_ITEMS, start=1):
            console.print(f"  [muted]{i:>2}.[/] {label}")
        console.print("  [muted] 0.[/] Back to main menu")

        choice = ask_int_optional("Choose an option")
        if choice is None or choice == 0:
            break
        if not (1 <= choice <= len(_MENU_ITEMS)):
            error("Invalid option.")
            continue

        _, handler = _MENU_ITEMS[choice - 1]
        run_handler(handler, gw)

        pause()
