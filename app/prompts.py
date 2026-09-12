"""
Blocking terminal input helpers.

Responsible for:
    - Small user-input helpers (yes/no, integer choice in range, one of
      a fixed set of choices).

These block on ``input()`` and therefore must only ever be imported by
the interactive CLI (``app/cli.py``) -- never by the web server or any
other module that might run without a terminal attached.
"""

from __future__ import annotations

from typing import Optional


def prompt_choice(prompt: str, valid_choices: list[str]) -> str:
    """Prompt until the user enters one of ``valid_choices`` (case-insensitive)."""
    valid_lower = {c.lower() for c in valid_choices}
    while True:
        answer = input(prompt).strip()
        if answer.lower() in valid_lower:
            return answer
        print(f"  Please enter one of: {', '.join(valid_choices)}")


def prompt_yes_no(prompt: str, default: Optional[bool] = None) -> bool:
    """Prompt for a yes/no answer."""
    suffix = " [Y/n]: " if default is True else (" [y/N]: " if default is False else " [y/n]: ")
    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer and default is not None:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please answer 'y' or 'n'.")


def prompt_int_in_range(prompt: str, low: int, high: int) -> int:
    """Prompt until the user enters an integer within [low, high]."""
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            print(f"  Please enter a number between {low} and {high}.")
            continue
        if low <= value <= high:
            return value
        print(f"  Please enter a number between {low} and {high}.")
