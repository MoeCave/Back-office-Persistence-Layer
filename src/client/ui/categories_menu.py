"""
client/ui/categories_menu.py — Categories submenu adapted for the TCP client.
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

# ── Table renderer ───────────────────────────────────────────────────────────


def _category_table(
    categories: list[dict[str, Any]], title: str = "Categories"
) -> Table:
    t = make_table(
        "ID", "Name", "Belt", "Gender", "Min kg", "Max kg", title=title
    )
    for c in categories:
        t.add_row(
            str(c.get("category_id", "—")),
            c.get("name", "—"),
            c.get("belt_level") or "—",
            c.get("gender") or "—",
            (
                str(c.get("weight_min_kg"))
                if c.get("weight_min_kg") is not None
                else "—"
            ),
            (
                str(c.get("weight_max_kg"))
                if c.get("weight_max_kg") is not None
                else "—"
            ),
        )
    return t


# ── CRUD ─────────────────────────────────────────────────────────────────────


def _create(gw: ServerGateway) -> None:
    section("Create Category")
    name = ask("Category name (e.g. 'Blue -70kg Female')")
    if not name:
        error("Name is required.")
        return

    belt = ask_optional("Belt level (e.g. blue, black)")
    gender = ask_optional("Gender (M / F / Mixed)")
    weight_min = ask_float_optional("Min weight (kg)")
    weight_max = ask_float_optional("Max weight (kg)")

    try:
        c = gw.categories.create(
            name=name,
            belt_level=belt,
            gender=gender,
            weight_min_kg=weight_min,
            weight_max_kg=weight_max,
        )
        success(f"Category created — ID {c['category_id']}: {c['name']}")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _list_all(gw: ServerGateway) -> None:
    section("All Categories")
    cats = gw.categories.list_all()
    if not cats:
        empty_table_msg("categories")
    else:
        console.print(_category_table(cats))


def _read_by_id(gw: ServerGateway) -> None:
    section("Get Category by ID")
    cid = ask_int_optional("Category ID")
    if cid is None:
        return

    c = gw.categories.get(cid)
    if c is None:
        error(f"No category with ID {cid}.")
        return

    console.print(_category_table([c], title=f"Category #{cid}"))

    console.print(
        f"\n  Relationship [bold]N:M+attrs[/]  {rel_badge('N:M+attrs')}"
    )
    info(
        f"  Registrations in this category: {c.get('total_registrations', 0)}"
    )

    console.print(
        f"\n  Relationship [bold]1:N[/] — Matches  {rel_badge('1:N')}"
    )
    info(f"  Total matches in this category: {c.get('total_matches', 0)}")


def _update(gw: ServerGateway) -> None:
    section("Update Category")
    cid = ask_int_optional("Category ID to update")
    if cid is None:
        return

    c = gw.categories.get(cid)
    if c is None:
        error(f"No category with ID {cid}.")
        return

    info(f"  Editing: {c['name']}")
    new_name = ask(f"Name [{c['name']}]", default=c["name"]) or c["name"]
    new_belt = (
        ask(
            f"Belt [{c.get('belt_level') or ''}]",
            default=c.get("belt_level") or "",
        )
        or None
    )
    new_gender = (
        ask(f"Gender [{c.get('gender') or ''}]", default=c.get("gender") or "")
        or None
    )

    min_raw = ask(
        f"Min kg [{c.get('weight_min_kg') or ''}]",
        default=str(c.get("weight_min_kg") or ""),
    )
    max_raw = ask(
        f"Max kg [{c.get('weight_max_kg') or ''}]",
        default=str(c.get("weight_max_kg") or ""),
    )
    try:
        new_min = float(min_raw) if min_raw else None
    except ValueError:
        new_min = c.get("weight_min_kg")
    try:
        new_max = float(max_raw) if max_raw else None
    except ValueError:
        new_max = c.get("weight_max_kg")

    try:
        gw.categories.update(
            cid,
            name=new_name,
            belt_level=new_belt,
            gender=new_gender,
            weight_min_kg=new_min,
            weight_max_kg=new_max,
        )
        success(f"Category #{cid} updated.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


def _delete(gw: ServerGateway) -> None:
    section("Delete Category")
    cid = ask_int_optional("Category ID to delete")
    if cid is None:
        return

    c = gw.categories.get(cid)
    if c is None:
        error(f"No category with ID {cid}.")
        return

    if not ask_bool(
        f"Delete category '{c['name']}'? "
        "(registrations and matches will lose reference)",
        False,
    ):
        info("Cancelled.")
        return

    try:
        gw.categories.delete(cid)
        success(f"Category #{cid} deleted.")
    except (ServerError, ValueError) as exc:
        error(str(exc))


# ── Searches ─────────────────────────────────────────────────────────────────


def _filter_by_name(gw: ServerGateway) -> None:
    section("Search by Name")
    name = ask("Name (partial match)")
    results = gw.categories.get_by_name(name)
    if not results:
        info(f"No categories matching '{name}'.")
    else:
        console.print(_category_table(results))


def _filter_by_belt(gw: ServerGateway) -> None:
    section("Filter by Belt Level")
    belt = ask("Belt level")
    results = gw.categories.get_by_belt_level(belt)
    if not results:
        info(f"No categories with belt '{belt}'.")
    else:
        console.print(_category_table(results))


def _filter_by_gender(gw: ServerGateway) -> None:
    section("Filter by Gender")
    gender = ask("Gender (M / F / Mixed)")
    results = gw.categories.get_by_gender(gender)
    if not results:
        info(f"No categories for gender '{gender}'.")
    else:
        console.print(_category_table(results))


def _filter_by_weight(gw: ServerGateway) -> None:
    section("Filter by Weight Range")
    min_kg = ask_float_optional(
        "Min weight (kg) — leave blank for no lower bound"
    )
    max_kg = ask_float_optional(
        "Max weight (kg) — leave blank for no upper bound"
    )
    results = gw.categories.get_by_weight_range(min_kg=min_kg, max_kg=max_kg)
    if not results:
        info("No categories in that weight range.")
    else:
        console.print(
            _category_table(results, title=f"Weight {min_kg}–{max_kg} kg")
        )


# ── Submenu ──────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all categories", _list_all),
    ("Get category by ID", _read_by_id),
    ("Create category", _create),
    ("Update category", _update),
    ("Delete category", _delete),
    ("Search by name", _filter_by_name),
    ("Filter by belt level", _filter_by_belt),
    ("Filter by gender", _filter_by_gender),
    ("Filter by weight range", _filter_by_weight),
]


def categories_menu(gw: ServerGateway) -> None:
    while True:
        section("Categories")
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
