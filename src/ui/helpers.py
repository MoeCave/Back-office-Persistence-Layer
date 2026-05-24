"""
UI helper functions: prompts, confirmations, table builders, pickers.
All input/output goes through the shared `console` object.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, TypeVar

from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from .console import console

T = TypeVar("T")


# ── Input helpers ──────────────────────────────────────────────────────────────

def ask(label: str, default: str = "") -> str:
    """Ask for a string value. Empty input returns the default."""
    result = Prompt.ask(f"[prompt]  {label}[/]", default=default, console=console)
    return result.strip()


def ask_optional(label: str) -> Optional[str]:
    """Ask for an optional string. Blank input → None."""
    result = Prompt.ask(f"[prompt]  {label} (leave blank to skip)[/]", default="", console=console)
    result = result.strip()
    return result if result else None


def ask_int(label: str, default: Optional[int] = None) -> int:
    """Ask for a required integer."""
    if default is not None:
        return IntPrompt.ask(f"[prompt]  {label}[/]", default=default, console=console)
    return IntPrompt.ask(f"[prompt]  {label}[/]", console=console)


def ask_int_optional(label: str) -> Optional[int]:
    """Ask for an optional integer. Blank → None."""
    raw = ask_optional(label)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        console.print("[error]  Not a valid number — skipped.[/]")
        return None


def ask_float_optional(label: str) -> Optional[float]:
    """Ask for an optional float. Blank → None."""
    raw = ask_optional(label)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        console.print("[error]  Not a valid number — skipped.[/]")
        return None


def ask_bool(label: str, default: bool = False) -> bool:
    """Ask a yes/no question."""
    return Confirm.ask(f"[prompt]  {label}[/]", default=default, console=console)


def choose_from_list(items: List[T], label_fn: Callable[[T], str], title: str) -> Optional[T]:
    """
    Display a numbered list and let the user pick one item.
    Returns the selected item, or None if the user cancels.
    """
    if not items:
        console.print(f"[warning]  No {title} available.[/]")
        return None

    console.print(f"\n[header]  {title}[/]")
    for i, item in enumerate(items, start=1):
        console.print(f"  [muted]{i:>3}.[/] {label_fn(item)}")
    console.print(f"  [muted]  0.[/] Cancel")

    while True:
        choice = IntPrompt.ask(f"[prompt]  Choose[/]", default=0, console=console)
        if choice == 0:
            return None
        if 1 <= choice <= len(items):
            return items[choice - 1]
        console.print(f"[error]  Enter a number between 0 and {len(items)}.[/]")


def paginate_list(items: List[T], page_size: int = 10) -> None:
    """Print items in paginated chunks, waiting for input between pages."""
    total = len(items)
    if total == 0:
        return
    start = 0
    while start < total:
        end = min(start + page_size, total)
        yield items[start:end]
        start = end
        if start < total:
            cont = Confirm.ask(
                f"[muted]  Showing {end}/{total}. Continue?[/]",
                default=True,
                console=console,
            )
            if not cont:
                break


# ── Display helpers ────────────────────────────────────────────────────────────

def section(title: str) -> None:
    """Print a styled section header."""
    console.print()
    console.rule(f"[title]{title}[/]")


def success(msg: str) -> None:
    console.print(f"\n[success]  ✓ {msg}[/]\n")


def error(msg: str) -> None:
    console.print(f"\n[error]  ✗ {msg}[/]\n")


def info(msg: str) -> None:
    console.print(f"[info]  {msg}[/]")


def show_panel(title: str, content: str, style: str = "cyan") -> None:
    console.print(Panel(content, title=f"[bold]{title}[/]", border_style=style))


def empty_table_msg(entity: str) -> None:
    console.print(f"[muted]  No {entity} found.[/]")


def rel_badge(kind: str) -> Text:
    """Return a styled relationship badge for table display."""
    badges = {
        "1:1":        Text("1:1",        style="rel_1_1 bold"),
        "1:N":        Text("1:N",        style="rel_1_n bold"),
        "N:M":        Text("N:M",        style="rel_n_m bold"),
        "N:M+attrs":  Text("N:M+attrs",  style="rel_n_m_attr bold"),
    }
    return badges.get(kind, Text(kind))


def make_table(*headers: str, title: str = "") -> Table:
    """Create a Rich Table with consistent styling."""
    t = Table(title=title, show_header=True, header_style="header",
              border_style="dim", expand=False, highlight=True)
    for h in headers:
        t.add_column(h)
    return t


def pause() -> None:
    """Wait for the user to press Enter before continuing."""
    Prompt.ask("\n[muted]  Press Enter to continue[/]", default="", console=console)
