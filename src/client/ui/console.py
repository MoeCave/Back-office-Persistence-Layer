"""
Shared Rich console instance and styling helpers used across all UI menus.
"""

from rich.console import Console
from rich.theme import Theme

APP_THEME = Theme(
    {
        "title": "bold cyan",
        "header": "bold white",
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "dim white",
        "prompt": "bold magenta",
        "muted": "dim",
        "rel_1_1": "cyan",
        "rel_1_n": "green",
        "rel_n_m": "yellow",
        "rel_n_m_attr": "magenta",
    }
)

console = Console(theme=APP_THEME)
