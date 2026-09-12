"""
Input validation helpers.

Responsible for:
    - Validating / normalizing destination paths.

URL validation lives in :mod:`app.sites` (site-agnostic, backed by
yt-dlp's own extractor registry) -- this module only keeps the
filesystem-path checks, which have nothing to do with any particular
site. Terminal input helpers (yes/no, int-in-range, etc.) live in
:mod:`app.prompts`, kept out of here so this module stays safe to
import from non-interactive contexts (e.g. a future web server).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple


class ValidationError(Exception):
    """Raised for user-facing validation failures."""


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
