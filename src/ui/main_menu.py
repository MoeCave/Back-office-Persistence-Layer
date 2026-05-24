"""
Main menu — application entry point.

Shows a header with the relationship legend, then routes to each submenu.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .console import console
from .helpers import ask_int_optional, error, rel_badge, section
from .fighters_menu import fighters_menu
from .tournaments_menu import tournaments_menu
from .categories_menu import categories_menu
from .matches_menu import matches_menu
from .registrations_menu import registrations_menu


def _print_header() -> None:
    legend = Table.grid(padding=(0, 2))
    legend.add_column(style="bold")
    legend.add_column()
    legend.add_row(rel_badge("1:1"),       "Fighter ↔ MedicalRecord")
    legend.add_row(rel_badge("1:N"),       "Tournament → Tatami / Match")
    legend.add_row(rel_badge("N:M"),       "Match ↔ Fighter (blue / red / winner)")
    legend.add_row(rel_badge("N:M+attrs"), "Fighter ↔ Category ↔ Tournament  (weight, approval)")

    console.print(
        Panel(
            legend,
            title="[bold cyan]🥋  Tournament Back-Office Manager[/]",
            subtitle="[dim]Relationship legend[/]",
            border_style="cyan",
            padding=(1, 3),
        )
    )


_SUBMENUS = [
    ("Fighters          (1:1 MedicalRecord · N:M+attrs Registration)", fighters_menu),
    ("Tournaments       (1:N Tatami · 1:N Match · N:M+attrs Registration)", tournaments_menu),
    ("Categories        (N:M+attrs Registration · 1:N Match)", categories_menu),
    ("Matches           (N:M Fighter · N:M Category/Tournament)", matches_menu),
    ("Registrations     N:M+attrs  Fighter ↔ Category ↔ Tournament", registrations_menu),
]


def run_main_menu(session_factory) -> None:
    """Start the interactive console UI."""
    while True:
        console.clear()
        _print_header()
        section("Main Menu")

        for i, (label, _) in enumerate(_SUBMENUS, start=1):
            console.print(f"  [muted]{i}.[/] {label}")
        console.print(f"  [muted]0.[/] Exit")

        choice = ask_int_optional("Choose a section")
        if choice is None or choice == 0:
            console.print("\n[success]  Goodbye! 👋[/]\n")
            break
        if not (1 <= choice <= len(_SUBMENUS)):
            error("Invalid option.")
            continue

        _, submenu_fn = _SUBMENUS[choice - 1]
        submenu_fn(session_factory)
