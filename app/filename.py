"""
Filename generation and sanitization.

Responsible for:
    - Turning a filename mode (original / numbered / pattern) plus video
      metadata into a final, safe filename (without extension).
    - Sanitizing filenames so they are valid on both Windows and Linux.
    - Preserving Unicode (e.g. Arabic) titles wherever possible.

Supported placeholders for custom patterns:
    {number}          Sequential position, 1-based (same as {playlist_index}
                       for playlists; for single videos it's always 1).
    {title}            The video's title as reported by yt-dlp.
    {playlist_index}   1-based position within the playlist (alias of
                       {number} for playlist downloads).
    {uploader}         The channel / uploader name.
"""

from __future__ import annotations

import glob as _glob
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Windows reserved device names (case-insensitive), which are invalid as a
# filename (with or without an extension) on Windows.
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Characters invalid in filenames on Windows. Linux only truly forbids
# '/' and the NUL byte, but we sanitize for the stricter Windows rule set
# on all platforms so filenames stay portable, per the project's Windows +
# Linux cross-platform requirement.
_WINDOWS_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')

# Control characters (0x00-0x1F) are invalid on Windows and inadvisable
# anywhere.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f]")

_MAX_COMPONENT_LENGTH = 150  # conservative, well under the 255-byte limits


class FilenameError(Exception):
    """Raised for invalid filename patterns or generation failures."""


def sanitize_filename(name: str, fallback: str = "video") -> str:
    """Make ``name`` safe to use as a filename on Windows and Linux.

    Preserves Unicode characters (Arabic, etc.) -- only strips characters
    that are actually illegal, plus leading/trailing dots and spaces
    (which Windows silently trims / rejects).
    """
    if name is None:
        name = ""
    name = str(name)

    name = _CONTROL_CHARS.sub("", name)
    name = _WINDOWS_INVALID_CHARS.sub("_", name)

    # Windows disallows trailing dots and spaces in path components.
    name = name.strip().rstrip(". ")

    # Collapse whitespace runs (including ones introduced by stripping)
    # into single spaces for readability.
    name = re.sub(r"\s+", " ", name).strip()

    if not name:
        name = fallback

    if name.upper() in _WINDOWS_RESERVED_NAMES:
        name = f"_{name}"

    if len(name) > _MAX_COMPONENT_LENGTH:
        name = name[:_MAX_COMPONENT_LENGTH].rstrip(". ")
        if not name:
            name = fallback

    return name


_PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")

_SUPPORTED_PLACEHOLDERS = {"number", "title", "playlist_index", "uploader"}


def validate_pattern(pattern: str) -> None:
    """Raise :class:`FilenameError` if ``pattern`` uses unknown placeholders."""
    if not pattern or not pattern.strip():
        raise FilenameError("The filename pattern cannot be empty.")
    used = set(_PLACEHOLDER_PATTERN.findall(pattern))
    unknown = used - _SUPPORTED_PLACEHOLDERS
    if unknown:
        raise FilenameError(
            f"Unknown placeholder(s) in pattern: {', '.join(sorted(unknown))}. "
            f"Supported placeholders: {', '.join(sorted(_SUPPORTED_PLACEHOLDERS))}"
        )


def build_filename(
    mode: str,
    index: int,
    metadata: Dict[str, Any],
    pattern: Optional[str] = None,
) -> str:
    """Build a sanitized filename (without extension) for one video.

    Args:
        mode: One of "original", "numbered", "pattern".
        index: 1-based position of this video (1 for a single video,
            or the playlist position for playlist items).
        metadata: Dict with keys like "title" and "uploader" (as returned
            by yt-dlp's ``extract_info``).
        pattern: Required when mode == "pattern".
    """
    title = metadata.get("title") or "video"
    uploader = metadata.get("uploader") or "unknown"

    if mode == "original":
        return sanitize_filename(title, fallback=f"video_{index}")

    if mode == "numbered":
        return sanitize_filename(str(index), fallback=str(index))

    if mode == "pattern":
        if not pattern:
            raise FilenameError("A filename pattern is required for pattern mode.")
        validate_pattern(pattern)
        values = {
            "number": str(index),
            "playlist_index": str(index),
            "title": title,
            "uploader": uploader,
        }
        try:
            rendered = pattern.format(**values)
        except (KeyError, IndexError) as exc:
            raise FilenameError(f"Invalid pattern '{pattern}': {exc}") from exc
        return sanitize_filename(rendered, fallback=f"video_{index}")

    raise FilenameError(f"Unknown filename mode: {mode}")


# Container extensions yt-dlp might produce for finished media output --
# used by existing_outputs() to recognize "this item was already
# downloaded" without assuming a fixed .mp4/.mp3 extension (some sites
# only offer webm/mkv/opus, etc). Deliberately excludes sidecar files
# yt-dlp can also write (.part, .ytdl, .info.json, .description,
# thumbnails) so those don't get mistaken for a finished download.
_MEDIA_EXTENSIONS = {
    "mp4", "mkv", "webm", "mov", "avi", "flv", "m4v",
    "mp3", "m4a", "opus", "ogg", "aac", "flac", "wav", "wma",
}


def existing_outputs(destination: Path, stem: str) -> List[Path]:
    """Find already-downloaded media file(s) for ``stem`` in ``destination``.

    Used instead of checking for a single hardcoded extension (e.g.
    always ``.mp4``), since the real output container depends on what
    the site actually offers and how it got merged/remuxed.
    """
    pattern = _glob.escape(stem) + ".*"
    return [
        path
        for path in sorted(destination.glob(pattern))
        if path.is_file() and path.suffix.lower().lstrip(".") in _MEDIA_EXTENSIONS
    ]


# Subtitle file extensions yt-dlp can produce (a language code precedes
# this in the filename, e.g. "<stem>.en.srt") -- used by
# existing_subtitle_outputs() the same way _MEDIA_EXTENSIONS is used by
# existing_outputs(), for a subtitles-only download where there is no
# media file to check for.
_SUBTITLE_EXTENSIONS = {"srt", "vtt", "ass", "ssa", "sbv", "ttml"}


def existing_subtitle_outputs(destination: Path, stem: str) -> List[Path]:
    """Find already-downloaded subtitle file(s) for ``stem`` in ``destination``."""
    pattern = _glob.escape(stem) + ".*"
    return [
        path
        for path in sorted(destination.glob(pattern))
        if path.is_file() and path.suffix.lower().lstrip(".") in _SUBTITLE_EXTENSIONS
    ]


def dedupe_path(path):
    """Return a non-colliding path by appending ' (2)', ' (3)', ... if needed.

    ``path`` is a pathlib.Path. Kept here (rather than in downloader.py)
    since it's a pure filename concern.
    """
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
