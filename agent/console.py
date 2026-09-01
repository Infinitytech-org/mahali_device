"""Affichage console soigné pour l'agent Mahali (couleurs ANSI, encadrés).

Aucune dépendance externe : fonctionne sur un Pi vierge. Les couleurs se
désactivent automatiquement si la sortie n'est pas un terminal.
"""

from __future__ import annotations

import os
import sys

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

# Palette Mahali
GREEN = "\033[38;2;153;255;11m" if _TTY else ""   # lime #99FF0B
OLIVE = "\033[38;2;90;140;40m" if _TTY else ""
DIM = "\033[2m" if _TTY else ""
BOLD = "\033[1m" if _TTY else ""
RED = "\033[38;5;203m" if _TTY else ""
YELLOW = "\033[38;5;221m" if _TTY else ""
CYAN = "\033[38;5;80m" if _TTY else ""
RESET = "\033[0m" if _TTY else ""

_W = 58

BANNER = f"""{GREEN}{BOLD}
   __  __       _           _ _
  |  \\/  |     | |         | (_)
  | \\  / | __ _| |__   __ _| |_
  | |\\/| |/ _` | '_ \\ / _` | | |
  | |  | | (_| | | | | (_| | | |
  |_|  |_|\\__,_|_| |_|\\__,_|_|_|   {RESET}{DIM}contrôleur de serre{RESET}
"""


def banner() -> None:
    print(BANNER)


def rule() -> None:
    print(f"{DIM}{'─' * _W}{RESET}")


def title(text: str) -> None:
    print(f"\n{BOLD}{text}{RESET}")
    rule()


def info(text: str) -> None:
    print(f"  {text}")


def ok(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}!{RESET} {text}")


def error(text: str) -> None:
    print(f"  {RED}✗{RESET} {text}")


def step(text: str) -> None:
    print(f"{CYAN}➜{RESET} {text}")


def kv(label: str, value: str, good: bool | None = None) -> None:
    mark = ""
    if good is True:
        mark = f"{GREEN}●{RESET} "
    elif good is False:
        mark = f"{RED}○{RESET} "
    print(f"  {mark}{label:<22}{DIM}{value}{RESET}")


def big_code(code: str) -> None:
    """Affiche le device_id bien en évidence (l'utilisateur doit le recopier)."""
    line = f"   {code}   "
    pad = "═" * (len(line))
    print(f"\n{GREEN}{BOLD}  ╔{pad}╗{RESET}")
    print(f"{GREEN}{BOLD}  ║{line}║{RESET}")
    print(f"{GREEN}{BOLD}  ╚{pad}╝{RESET}\n")


def ask(prompt: str) -> str:
    return input(f"{BOLD}{prompt}{RESET} ").strip()
