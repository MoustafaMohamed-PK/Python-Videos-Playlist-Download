"""
Format / quality handling.

Responsible for:
    - Retrieving the available formats for a video via yt-dlp (no download).
    - Mapping a user-facing quality choice (e.g. "1080p") to a concrete
      yt-dlp format selector string.
    - Reporting which qualities are actually available for a given video,
      so the CLI can tell the user honestly rather than silently
      substituting a different quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Ordered from highest to lowest so we can present a sensible menu and
# also do "closest available" reporting.
QUALITY_LADDER = [
    ("best", "Best available"),
    ("2160p", "2160p (4K)"),
    ("1440p", "1440p"),
    ("1080p", "1080p"),
    ("720p", "720p"),
    ("480p", "480p"),
    ("360p", "360p"),
    ("audio", "Audio only"),
]

_HEIGHT_BY_LABEL = {
    "2160p": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}


@dataclass
class QualityChoice:
    label: str  # e.g. "1080p", "best", "audio"

    @property
    def is_audio_only(self) -> bool:
        return self.label == "audio"

    @property
    def is_best(self) -> bool:
        return self.label == "best"

    @property
    def height(self) -> Optional[int]:
        return _HEIGHT_BY_LABEL.get(self.label)


def build_format_selector(choice: QualityChoice) -> str:
    """Translate a :class:`QualityChoice` into a yt-dlp ``format`` selector.

    yt-dlp handles the video+audio merge automatically (via ffmpeg) when
    the chosen video format has no audio track -- we just need to express
    "best video at this height or below, plus best audio" and let yt-dlp
    pick separate streams and merge them if necessary.

    We prefer H.264 video (``avc1``) + AAC audio (``mp4a``) whenever a
    stream in that codec pair is available at the target height: YouTube
    also serves VP9/AV1 video, which yt-dlp's default ranking treats as
    "better" and will pick over H.264 at the same resolution. Those
    codecs mux into a valid .mp4 container, but many common players
    (Windows' built-in video app, older VLC/QuickTime builds, TVs, some
    phone galleries) can't decode AV1/VP9 -- they open the file and play
    the audio track while showing no picture. Falling back to "any
    codec" only when the compatible pair isn't available keeps quality
    intact while defaulting to the combination that actually plays
    everywhere.
    """
    if choice.is_audio_only:
        # Always transcoded to mp3 by the FFmpegExtractAudio postprocessor,
        # so the source audio codec doesn't affect playback compatibility.
        return "bestaudio/best"

    # NOTE: "+" binds tighter than "/" in yt-dlp's selector language
    # ("A+B/C" parses as "(A+B)/C"), so each fallback tier below is
    # written as a complete "video+audio" alternative rather than
    # nesting a "/" fallback inside one side of a "+" -- that would let
    # the parser peel it off into its own audio-only top-level
    # alternative and silently produce a video-less merge.
    if choice.is_best:
        return (
            "bestvideo*[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            "bestvideo*+bestaudio/best"
        )

    height = choice.height
    if height is None:
        # Defensive fallback; shouldn't happen given the fixed ladder.
        return (
            "bestvideo*[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            "bestvideo*+bestaudio/best"
        )

    # Exact-height-or-below, preferring an H.264+AAC combo for maximum
    # playback compatibility, then any codec combo of that size, then a
    # single progressive stream, then an unrestricted best-effort merge.
    return (
        f"bestvideo*[vcodec^=avc1][height<={height}]+bestaudio[acodec^=mp4a]/"
        f"bestvideo*[height<={height}]+bestaudio/"
        f"best[height<={height}]/"
        f"bestvideo*+bestaudio/best"
    )


def available_heights(formats: List[Dict[str, Any]]) -> List[int]:
    """Extract the distinct video heights available from yt-dlp format list."""
    heights = set()
    for fmt in formats:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if height and vcodec and vcodec != "none":
            heights.add(int(height))
    return sorted(heights, reverse=True)


def has_audio_only(formats: List[Dict[str, Any]]) -> bool:
    for fmt in formats:
        if fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none"):
            return True
    return False


def describe_available_qualities(formats: List[Dict[str, Any]]) -> List[str]:
    """Human-readable list of qualities actually available, high to low.

    Used to tell the user what *is* available when their choice isn't.
    """
    heights = available_heights(formats)
    labels = []
    for label, height in _HEIGHT_BY_LABEL.items():
        if height in heights:
            labels.append(label)
    # Sort by descending height to match the ladder order.
    labels.sort(key=lambda l: _HEIGHT_BY_LABEL[l], reverse=True)
    if has_audio_only(formats):
        labels.append("audio")
    return labels


def quality_is_available(choice: QualityChoice, formats: List[Dict[str, Any]]) -> bool:
    """Check whether the requested quality can plausibly be satisfied.

    "best" is always considered available if there is at least one format.
    Exact heights must match a real available height (we don't silently
    upgrade/downgrade -- the caller decides what to do if this is False).
    """
    if not formats:
        return False
    if choice.is_best:
        return True
    if choice.is_audio_only:
        return has_audio_only(formats)
    heights = available_heights(formats)
    return choice.height in heights
