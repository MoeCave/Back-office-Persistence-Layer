"""
Categories submenu — CRUD and filter operations.

Categories are lookup entities (no aggregation children that need
special handling in the UI), but they participate in:
  - N:M+attrs  Category ↔ Fighter ↔ Tournament (registrations)
  - 1:N        Category → Match
"""

from __future__ import annotations

from rich.table import Table

from src.domain.models import Category
from src.domain.repositories import UnitOfWork

from .console import console
from .helpers import (
    ask, ask_float_optional, ask_int_optional, ask_optional,
    empty_table_msg, error, info, make_table, pause, rel_badge,
    section, success,
)


# ── Table renderer ─────────────────────────────────────────────────────────────

def _category_table(categories: list[Category], title: str = "Categories") -> Table:
    t = make_table("ID", "Name", "Belt", "Gender",
                   "Min kg", "Max kg", title=title)
    for c in categories:
        t.add_row(
            str(c.category_id),
            c.name,
            c.belt_level or "—",
            c.gender or "—",
            str(c.weight_min_kg) if c.weight_min_kg is not None else "—",
            str(c.weight_max_kg) if c.weight_max_kg is not None else "—",
        )
    return t


# ── CRUD ───────────────────────────────────────────────────────────────────────

def _create(uow: UnitOfWork) -> None:
    section("Create Category")
    name = ask("Category name (e.g. 'Blue -70kg Female')")
    if not name:
        error("Name is required.")
        return

    belt       = ask_optional("Belt level (e.g. blue, black)")
    gender     = ask_optional("Gender (M / F / Mixed)")
    weight_min = ask_float_optional("Min weight (kg)")
    weight_max = ask_float_optional("Max weight (kg)")

    c = Category(
        name=name,
        belt_level=belt,
        gender=gender,
        weight_min_kg=weight_min,
        weight_max_kg=weight_max,
    )
    uow.categories.add(c)
    uow.commit()
    success(f"Category created — ID {c.category_id}: {c.name}")


def _list_all(uow: UnitOfWork) -> None:
    section("All Categories")
    cats = uow.categories.get_all()
    if not cats:
        empty_table_msg("categories")
    else:
        console.print(_category_table(cats))


def _read_by_id(uow: UnitOfWork) -> None:
    section("Get Category by ID")
    cid = ask_int_optional("Category ID")
    if cid is None:
        return

    c = uow.categories.get(cid)
    if c is None:
        error(f"No category with ID {cid}.")
        return

    console.print(_category_table([c], title=f"Category #{cid}"))

    # ── N:M+attrs Registrations ────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]N:M+attrs[/]  {rel_badge('N:M+attrs')}")
    info(f"  Registrations in this category: {len(c.registrations)}")

    # ── 1:N Matches ────────────────────────────────────────────────────────────
    console.print(f"\n  Relationship [bold]1:N[/] — Matches  {rel_badge('1:N')}")
    info(f"  Total matches in this category: {len(c.matches)}")


def _update(uow: UnitOfWork) -> None:
    section("Update Category")
    cid = ask_int_optional("Category ID to update")
    if cid is None:
        return

    c = uow.categories.get(cid)
    if c is None:
        error(f"No category with ID {cid}.")
        return

    info(f"  Editing: {c.name}")
    c.name       = ask(f"Name [{c.name}]", default=c.name) or c.name
    c.belt_level = ask(f"Belt [{c.belt_level or ''}]", default=c.belt_level or "") or None
    c.gender     = ask(f"Gender [{c.gender or ''}]",   default=c.gender or "")     or None

    min_raw = ask(f"Min kg [{c.weight_min_kg or ''}]", default=str(c.weight_min_kg or ""))
    max_raw = ask(f"Max kg [{c.weight_max_kg or ''}]", default=str(c.weight_max_kg or ""))
    try:
        c.weight_min_kg = float(min_raw) if min_raw else None
    except ValueError:
        pass
    try:
        c.weight_max_kg = float(max_raw) if max_raw else None
    except ValueError:
        pass

    uow.categories.update(c)
    uow.commit()
    success(f"Category #{cid} updated.")


def _delete(uow: UnitOfWork) -> None:
    section("Delete Category")
    cid = ask_int_optional("Category ID to delete")
    if cid is None:
        return

    c = uow.categories.get(cid)
    if c is None:
        error(f"No category with ID {cid}.")
        return

    from .helpers import ask_bool
    if not ask_bool(f"Delete category '{c.name}'? (registrations and matches will lose reference)", False):
        info("Cancelled.")
        return

    uow.categories.delete(c)
    uow.commit()
    success(f"Category #{cid} deleted.")


# ── Searches ───────────────────────────────────────────────────────────────────

def _filter_by_name(uow: UnitOfWork) -> None:
    section("Search by Name")
    name = ask("Name (partial match)")
    results = uow.categories.get_by_name(name)
    if not results:
        info(f"No categories matching '{name}'.")
    else:
        console.print(_category_table(results))


def _filter_by_belt(uow: UnitOfWork) -> None:
    section("Filter by Belt Level")
    belt = ask("Belt level")
    results = uow.categories.get_by_belt_level(belt)
    if not results:
        info(f"No categories with belt '{belt}'.")
    else:
        console.print(_category_table(results))


def _filter_by_gender(uow: UnitOfWork) -> None:
    section("Filter by Gender")
    gender = ask("Gender (M / F / Mixed)")
    results = uow.categories.get_by_gender(gender)
    if not results:
        info(f"No categories for gender '{gender}'.")
    else:
        console.print(_category_table(results))


def _filter_by_weight(uow: UnitOfWork) -> None:
    section("Filter by Weight Range")
    min_kg = ask_float_optional("Min weight (kg) — leave blank for no lower bound")
    max_kg = ask_float_optional("Max weight (kg) — leave blank for no upper bound")
    results = uow.categories.get_by_weight_range(min_kg=min_kg, max_kg=max_kg)
    if not results:
        info("No categories in that weight range.")
    else:
        console.print(_category_table(results, title=f"Weight {min_kg}–{max_kg} kg"))


# ── Submenu ────────────────────────────────────────────────────────────────────

_MENU_ITEMS = [
    ("List all categories",           _list_all),
    ("Get category by ID",            _read_by_id),
    ("Create category",               _create),
    ("Update category",               _update),
    ("Delete category",               _delete),
    ("Search by name",                _filter_by_name),
    ("Filter by belt level",          _filter_by_belt),
    ("Filter by gender",              _filter_by_gender),
    ("Filter by weight range",        _filter_by_weight),
]


def categories_menu(session_factory) -> None:
    while True:
        section("Categories")
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
