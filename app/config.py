"""
Configuration management for the YouTube Downloader.

Responsible for:
    - Providing sane default settings
    - Loading configuration from a JSON file (if present)
    - Saving configuration back to disk
    - Never persisting secrets (cookies, passwords, tokens)

The configuration file lives next to the application (``config.json``)
unless a different path is supplied.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_FILENAME = "config.json"

# Keys that must never be written to disk, even if somehow present in a
# dict that gets merged into the config. This is a defensive measure --
# nothing in this application currently collects these, but the guard
# stays cheap insurance against future accidental additions.
_FORBIDDEN_KEYS = {"cookies", "cookie", "password", "passwd", "token", "auth", "api_key"}


@dataclass
class AppConfig:
    """Holds all persisted user preferences."""

    download_folder: str = ""
    quality: str = "1080p"
    filename_mode: str = "original"  # original | numbered | pattern
    filename_pattern: str = "{title}"
    existing_file_behavior: str = "skip"  # skip | overwrite | ask
    concurrency: int = 3  # playlist items downloaded in parallel
    concurrent_fragments: int = 4  # yt-dlp's own DASH/HLS fragment parallelism, per item

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key in list(data.keys()):
            if key.lower() in _FORBIDDEN_KEYS:
                data.pop(key, None)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        config = cls(**clean)
        config.concurrency = max(1, min(8, config.concurrency))
        config.concurrent_fragments = max(1, min(8, config.concurrent_fragments))
        return config


class ConfigManager:
    """Loads and saves :class:`AppConfig` instances from/to a JSON file."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else Path(DEFAULT_CONFIG_FILENAME)

    def load(self) -> AppConfig:
        """Load configuration from disk, falling back to defaults.

        Never raises on a missing or corrupt file -- always returns a
        usable :class:`AppConfig`.
        """
        if not self.path.exists():
            return AppConfig()

        try:
            with self.path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                return AppConfig()
            return AppConfig.from_dict(raw)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # Corrupt or unreadable config -- fall back to defaults rather
            # than crashing the whole application.
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        """Persist configuration to disk, creating parent dirs if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = config.to_dict()
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp_path.replace(self.path)
