"""
Subtitle language menu.

Responsible for:
    - Extracting the set of subtitle languages yt-dlp reports available
      for a video (manual, human-authored captions and/or
      auto-generated ones), merged into one list a user can choose
      from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class SubtitleOption:
    """One selectable subtitle language."""

    lang: str  # yt-dlp language code, e.g. "en", "es" -- usable as a subtitleslangs entry
    label: str  # display text, e.g. "English" or "Spanish (auto-generated)"
    auto_only: bool  # True if no manual (human-authored) track exists for this language


def _track_name(tracks: List[Dict[str, Any]], lang: str) -> str:
    for track in tracks or []:
        name = track.get("name")
        if name:
            return name
    return lang


def available_subtitle_options(info: Dict[str, Any]) -> List[SubtitleOption]:
    """Build a subtitle language menu from a video's yt-dlp info dict.

    ``info`` is the raw dict from a non-flat extraction (e.g.
    ``ExtractedTarget.raw`` for a single video), since subtitle
    metadata isn't populated by flat playlist extraction.

    Manual subtitles and automatic captions are merged into one entry
    per language: a language with a manual track is labeled without
    qualification; one available only as an auto-generated caption is
    marked accordingly, since the accuracy differs and a user picking
    "English" would otherwise not know which they're getting. Manually
    captioned languages sort first, then auto-generated-only ones,
    each alphabetically by label.
    """
    manual: Dict[str, List[Dict[str, Any]]] = info.get("subtitles") or {}
    auto: Dict[str, List[Dict[str, Any]]] = info.get("automatic_captions") or {}

    options: List[SubtitleOption] = []
    for lang in set(manual) | set(auto):
        if lang in manual:
            options.append(SubtitleOption(lang=lang, label=_track_name(manual[lang], lang), auto_only=False))
        else:
            name = _track_name(auto[lang], lang)
            options.append(SubtitleOption(lang=lang, label=f"{name} (auto-generated)", auto_only=True))

    options.sort(key=lambda o: (o.auto_only, o.label.lower()))
    return options
