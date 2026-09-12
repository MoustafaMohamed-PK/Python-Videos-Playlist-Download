"""
Small cross-platform utility helpers.

Responsible for:
    - Detecting FFmpeg on PATH (cross-platform, no hardcoded paths).
    - Human-readable formatting (bytes, ETA, progress bars).
    - Logging setup.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional


def find_ffmpeg() -> Optional[str]:
    """Locate the ffmpeg executable via PATH, cross-platform.

    Returns the resolved path, or None if not found. Works on Windows
    (where the executable is ``ffmpeg.exe``) and Linux/macOS (``ffmpeg``)
    because ``shutil.which`` handles the platform-specific extension
    resolution itself.
    """
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def format_bytes(num_bytes: Optional[float]) -> str:
    """Format a byte count as a human-readable string (e.g. '125 MB')."""
    if num_bytes is None:
        return "unknown"
    num_bytes = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{int(num_bytes)} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_eta(seconds: Optional[float]) -> str:
    """Format a seconds count as HH:MM:SS (or MM:SS if under an hour)."""
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_speed(bytes_per_sec: Optional[float]) -> str:
    if not bytes_per_sec:
        return "-- MB/s"
    return f"{format_bytes(bytes_per_sec)}/s"


def render_progress_bar(fraction: float, width: int = 20) -> str:
    """Render a simple text progress bar, e.g. '[#####---------]'."""
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def setup_logging(log_dir: Path | str = "logs", filename: str = "downloader.log") -> logging.Logger:
    """Configure and return the application logger.

    Logs are written to ``<log_dir>/<filename>`` and never include
    authentication material -- callers must not pass cookies/tokens into
    log messages.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / filename

    logger = logging.getLogger("youtube_downloader")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if setup_logging is called more than once
    # (e.g. in tests).
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "_ytdl_marker", False)
               for h in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler._ytdl_marker = True  # type: ignore[attr-defined]
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
