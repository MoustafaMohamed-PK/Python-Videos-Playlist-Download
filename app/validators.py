"""
Input validation helpers.

Responsible for:
    - Validating that a string looks like a YouTube URL
    - Validating / normalizing destination paths
    - Small user-input helpers (yes/no, integer choice in range)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


class ValidationError(Exception):
    """Raised for user-facing validation failures."""


def is_youtube_url(url: str) -> bool:
    """Return True if ``url`` looks like a YouTube URL (video or playlist)."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc.lower()
    return host in _YOUTUBE_HOSTS


def looks_like_playlist(url: str) -> bool:
    """Heuristic: does the URL reference a playlist (``list=`` param)?"""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
    except ValueError:
        return False
    return "list" in query and bool(query["list"][0])


def validate_youtube_url(url: str) -> str:
    """Validate a YouTube URL, raising :class:`ValidationError` if invalid."""
    if not url or not url.strip():
        raise ValidationError("The URL cannot be empty.")
    url = url.strip()
    if not is_youtube_url(url):
        raise ValidationError(
            "That does not look like a valid YouTube URL. "
            "Expected something like https://www.youtube.com/watch?v=... "
            "or https://youtu.be/..."
        )
    return url


def validate_destination_path(path_str: str) -> Path:
    """Normalize a user-supplied destination folder string into a Path.

    Handles relative paths, absolute paths, ``~`` expansion, and paths
    containing spaces (the caller is responsible for not splitting on
    whitespace before this point -- read the whole line of input).
    """
    if not path_str or not path_str.strip():
        raise ValidationError("The destination folder cannot be empty.")
    cleaned = path_str.strip().strip('"').strip("'")
    try:
        path = Path(cleaned).expanduser()
    except (ValueError, OSError) as exc:
        raise ValidationError(f"'{path_str}' is not a valid path: {exc}") from exc
    return path


def ensure_writable_directory(path: Path) -> Tuple[bool, Optional[str]]:
    """Check that ``path`` exists, is a directory, and is writable.

    Returns (ok, error_message).
    """
    if not path.exists():
        return False, "does_not_exist"
    if not path.is_dir():
        return False, f"'{path}' exists but is not a directory."
    probe = path / ".ytdl_write_test.tmp"
    try:
        probe.touch()
        probe.unlink()
    except OSError:
        return False, f"Permission denied: cannot write to '{path}'."
    return True, None


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
