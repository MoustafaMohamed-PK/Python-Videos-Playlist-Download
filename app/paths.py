"""
Confining browser-supplied destination paths to a configured root.

Responsible for:
    - resolve_within(): turn a user-supplied relative subfolder string
      into a real Path guaranteed to stay under a configured root
      directory, rejecting absolute paths, traversal, and anything
      else that could otherwise turn a text field into an arbitrary
      file write on the server.

This is the only thing standing between the web UI's "subfolder" field
(and its file-serving endpoint) and the filesystem outside the
configured download root -- the CLI, in contrast, is trusted to type
any path directly since it already runs with the user's own shell
permissions.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional

from app.filename import sanitize_filename
from app.validators import ValidationError


def resolve_within(root: Path, relative: Optional[str]) -> Path:
    """Resolve ``relative`` as a subfolder of ``root``, refusing to escape it.

    ``relative`` is untrusted client input. Rejected outright: NUL
    bytes, backslashes (so a Windows-style ``..\\..`` or a UNC-style
    ``\\\\server\\share`` can't slip past a POSIX-only check), and any
    absolute path. Each remaining path component is sanitized with the
    same rules used for filenames, and ``.``/``..`` segments are
    dropped rather than honored. The result is checked against the
    root only *after* resolving symlinks, so an in-tree symlink
    pointing outside the root can't be used to escape it either.
    """
    root = root.resolve(strict=True)
    if not relative or not relative.strip():
        return root

    if "\x00" in relative or "\\" in relative:
        raise ValidationError("Invalid destination.")
    if PurePosixPath(relative).is_absolute():
        raise ValidationError("Invalid destination.")

    parts = [
        sanitize_filename(part)
        for part in PurePosixPath(relative).parts
        if part not in ("", ".", "..")
    ]
    candidate = root.joinpath(*parts).resolve()

    if candidate != root and root not in candidate.parents:
        raise ValidationError("Destination escapes the download root.")

    return candidate
