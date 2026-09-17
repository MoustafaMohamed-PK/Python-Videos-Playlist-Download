"""
Format / quality handling.

Responsible for:
    - Retrieving the available formats for a video via yt-dlp (no download).
    - Mapping a user-facing quality choice (e.g. "1080p") to a concrete
      yt-dlp format selector string.
    - Reporting which qualities are actually available for a given video,
      so the CLI can tell the user honestly rather than silently
      substituting a different quality.
    - Building a quality menu from a site's *actual* formats, since
      non-YouTube sites rarely offer the same fixed resolution ladder
      (Vimeo may top out at 540p, a single-format site may report no
      height at all, an audio site like SoundCloud has no video).
    - Deciding whether a site's formats are safe to force into an .mp4
      container (see :func:`formats_support_mp4`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Ordered from highest to lowest. Used as the playlist-download ladder
# (formats aren't known upfront there -- see app/downloader.py) and as
# the fallback menu when a site's real formats can't be determined.
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

_HEIGHT_LABEL_RE = re.compile(r"^(\d+)p$")

# H.264 video + AAC audio, under either naming: YouTube/Facebook report
# RFC 6381 codec strings ("avc1.64001F", "mp4a.40.2"), TikTok reports
# plain names ("h264", "aac").
_H264_AAC_FILTERS = ("[vcodec~='^(avc1|h264)']", "[acodec~='^(mp4a|aac)']")

# Excludes AV1/VP8/VP9 and H.265/HEVC video (TikTok's "bytevc1" is
# HEVC), which many players can't decode -- they show a black screen
# with sound. The "?" keeps formats whose vcodec is unknown -- e.g.
# Facebook's progressive "hd"/"sd" H.264 streams.
_COMPATIBLE_VCODEC_FILTER = "[vcodec!~=?'^(av0?1|vp0?[89]|hev|hvc|h265|bytevc)']"


@dataclass
class QualityChoice:
    label: str  # e.g. "1080p", "540p", "best", "audio"

    @property
    def is_audio_only(self) -> bool:
        return self.label == "audio"

    @property
    def is_best(self) -> bool:
        return self.label == "best"

    @property
    def height(self) -> Optional[int]:
        # Parsed from the label itself (any "<N>p") rather than looked
        # up in a fixed table, so heights outside the YouTube-shaped
        # ladder -- 540p, 240p, whatever a given site actually offers --
        # work the same way as the ones on QUALITY_LADDER.
        match = _HEIGHT_LABEL_RE.match(self.label)
        return int(match.group(1)) if match else None


@dataclass(frozen=True)
class QualityOption:
    """One entry in a quality menu built from a video's real formats."""

    key: str  # e.g. "best", "1080p", "540p", "audio" -- usable as a QualityChoice.label
    label: str  # display text
    height: Optional[int]


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

    Sites like Facebook are a trickier case: their separate video-only
    (DASH) streams can be AV1-only, while the H.264 video lives in a
    progressive stream ("hd"/"sd") whose codec yt-dlp reports as
    unknown. So before falling back to an any-codec merge, we try a
    progressive stream that isn't known to be AV1/VP9/HEVC -- otherwise
    the AV1 merge wins and plays as a black screen with sound. TikTok
    is similar: its highest quality is often HEVC ("bytevc1"), with
    H.264 only at a lower resolution.
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
    h264, aac = _H264_AAC_FILTERS
    height = choice.height
    if choice.is_best or height is None:
        # height is None is a defensive fallback; shouldn't happen given
        # the fixed ladder.
        return (
            f"bestvideo*{h264}+bestaudio{aac}/"
            f"best{_COMPATIBLE_VCODEC_FILTER}/"
            "bestvideo*+bestaudio/best"
        )

    # Exact-height-or-below, preferring an H.264+AAC combo for maximum
    # playback compatibility, then a compatible progressive stream (the
    # "?" lets through streams with unknown height, like Facebook's
    # "hd"), then any codec combo of that size, then a single
    # progressive stream, then an unrestricted best-effort merge.
    return (
        f"bestvideo*{h264}[height<={height}]+bestaudio{aac}/"
        f"best[height<=?{height}]{_COMPATIBLE_VCODEC_FILTER}/"
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
        # Lenient beyond has_audio_only(): a site that reports no video
        # heights at all (e.g. an audio-only extractor whose formats
        # don't set vcodec == "none" the way YouTube's do) still counts
        # as "audio available" -- there's nothing else it could be.
        return has_audio_only(formats) or not available_heights(formats)
    heights = available_heights(formats)
    return choice.height in heights


def build_quality_menu(formats: List[Dict[str, Any]]) -> List[QualityOption]:
    """Build a quality menu from a video's *actual* formats.

    Unlike the fixed :data:`QUALITY_LADDER` (which assumes YouTube's
    standard resolution set), this reflects whatever the site really
    offers: an odd height like 540p, no height at all (a single muxed
    format), or audio-only content. Always includes "best" when any
    format exists.
    """
    if not formats:
        return [QualityOption(key="best", label="Best available", height=None)]

    heights = available_heights(formats)
    audio_only = has_audio_only(formats)

    if not heights:
        # No video heights at all: either this is a pure-audio site
        # (SoundCloud) -- offer only "audio" -- or a site with a single
        # muxed format lacking height metadata, where "best" is the
        # only meaningful choice.
        if audio_only:
            return [QualityOption(key="audio", label="Audio only", height=None)]
        return [QualityOption(key="best", label="Best available", height=None)]

    options = [QualityOption(key="best", label="Best available", height=None)]
    for height in heights:
        options.append(QualityOption(key=f"{height}p", label=f"{height}p", height=height))
    if audio_only:
        options.append(QualityOption(key="audio", label="Audio only", height=None))
    return options


# Codec name prefixes yt-dlp itself considers safe to mux into an .mp4
# container (mirrors yt_dlp.utils.get_compatible_ext's COMPATIBLE_CODECS
# for 'mp4') -- used to decide whether forcing a remux to .mp4 makes
# sense for a given site's formats, rather than assuming every site's
# output is as mp4-friendly as YouTube's.
_MP4_COMPATIBLE_CODECS = {
    "av1", "hevc", "avc1", "mp4a", "ac-4", "h264", "aacl", "ec-3",
}


def _codec_family(codec: Optional[str]) -> Optional[str]:
    if not codec or codec == "none":
        return None
    # Mirrors yt-dlp's own sanitize_codec: take the part before the
    # first ".", drop any "0" characters (so "vp09" -> "vp9"), lowercase.
    return codec.split(".")[0].replace("0", "").lower()


def formats_support_mp4(formats: List[Dict[str, Any]]) -> bool:
    """Whether any of ``formats`` use a codec yt-dlp will happily mux into mp4.

    Used to decide whether the ``FFmpegVideoRemuxer`` postprocessor (a
    forced stream-copy to .mp4) is worth attaching. On a webm/vp9/opus
    -only site, forcing a remux to mp4 can fail or corrupt the output;
    skipping it there and letting ``merge_output_format`` pick a
    container that actually fits the codecs is the safer default.
    """
    for fmt in formats:
        if _codec_family(fmt.get("vcodec")) in _MP4_COMPATIBLE_CODECS:
            return True
        if _codec_family(fmt.get("acodec")) in _MP4_COMPATIBLE_CODECS:
            return True
    return False
