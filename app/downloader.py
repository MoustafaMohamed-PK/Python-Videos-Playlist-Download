"""
Download engine built on top of yt-dlp.

Responsible for:
    - Extracting metadata (without downloading) for a video or playlist.
    - Configuring yt-dlp options (format selector, output template,
      ffmpeg postprocessors, resume behavior).
    - Performing the actual download(s) with progress callbacks.
    - Translating yt-dlp / network errors into friendly, categorized
      exceptions the CLI can present without a traceback.

Nothing here talks to the terminal directly -- it reports progress and
results through plain callables/dataclasses so the CLI layer owns all
presentation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yt_dlp

from app.filename import build_filename, dedupe_path, existing_outputs
from app.formats import QualityChoice, build_format_selector
from app.utils import ffmpeg_available

logger = logging.getLogger("youtube_downloader")


class _SilentYtdlpLogger:
    """Swallows yt-dlp's own console output.

    yt-dlp writes warnings/errors straight to stderr even with
    ``quiet=True`` (quiet only suppresses informational/progress output).
    We want a single, friendly error message from *this* application
    instead of yt-dlp's raw text appearing as well, so every
    ``yt_dlp.YoutubeDL`` instance in this module is configured with this
    logger. The underlying exception (and its message) is still raised
    and handled via :func:`classify_ytdlp_error`.
    """

    def debug(self, msg: str) -> None:
        logger.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        logger.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        logger.warning("yt-dlp warning: %s", msg)

    def error(self, msg: str) -> None:
        logger.debug("yt-dlp (suppressed console error): %s", msg)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class DownloadAppError(Exception):
    """Base class for all user-facing download errors."""


class URLUnavailableError(DownloadAppError):
    """The video/playlist could not be found or accessed."""


class PrivateVideoError(DownloadAppError):
    """The video is private."""


class AgeRestrictedError(DownloadAppError):
    """The video requires authentication due to age restriction."""


class NetworkError(DownloadAppError):
    """A network-level failure occurred (timeout, DNS, connection reset)."""


class FFmpegRequiredError(DownloadAppError):
    """FFmpeg is required for the requested operation but not available."""


class UnsupportedFormatError(DownloadAppError):
    """The requested quality/format is not available for this video."""


class DiskSpaceError(DownloadAppError):
    """The destination disk appears to be out of space."""


class PermissionDeniedError(DownloadAppError):
    """The destination path could not be written to."""


def classify_ytdlp_error(exc: Exception) -> DownloadAppError:
    """Map a raw yt-dlp/OSError exception to a friendly, typed error."""
    message = str(exc).lower()

    if "private video" in message:
        return PrivateVideoError("This video is private and cannot be downloaded.")
    if "sign in to confirm your age" in message or "age" in message and "restrict" in message:
        return AgeRestrictedError(
            "This video is age-restricted and requires authentication to download."
        )
    if "video unavailable" in message:
        return URLUnavailableError("This video is unavailable.")
    if "this playlist does not exist" in message or "playlist does not exist" in message:
        return URLUnavailableError("This playlist does not exist or is unavailable.")
    if "unable to download webpage" in message or "urlopen error" in message or "name or service not known" in message:
        return NetworkError("A network error occurred. Please check your internet connection.")
    if "timed out" in message or "timeout" in message:
        return NetworkError("The connection timed out. Please try again.")
    if "no space left on device" in message:
        return DiskSpaceError("Insufficient disk space to complete the download.")
    if "permission denied" in message:
        return PermissionDeniedError("Permission denied while writing the downloaded file.")
    if "requested format is not available" in message:
        return UnsupportedFormatError("The requested quality/format is not available for this video.")
    if "ffmpeg" in message and "not found" in message:
        return FFmpegRequiredError(
            "FFmpeg was not found. FFmpeg is required to merge the selected "
            "video and audio streams. Please install FFmpeg and make sure "
            "it is available in PATH."
        )
    if "certificate" in message or "ssl" in message:
        return NetworkError(
            "A secure connection to the site could not be established "
            "(SSL/certificate error). Check your network/proxy settings "
            "and try again."
        )

    return DownloadAppError(f"An unexpected error occurred: {exc}")


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------

@dataclass
class VideoInfo:
    """Lightweight metadata for one video, as needed by the CLI/filename layer."""

    id: str
    title: str
    uploader: str = "unknown"
    duration: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedTarget:
    """Result of a metadata-only extraction (no download)."""

    is_playlist: bool
    playlist_title: Optional[str]
    videos: List[VideoInfo]
    formats: List[Dict[str, Any]]  # populated only for a single video
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProgressEvent:
    """One progress update, passed to the CLI's progress callback."""

    status: str  # "downloading" | "finished" | "error"
    video_index: int  # 1-based position within this run
    video_total: int
    title: str
    downloaded_bytes: Optional[float]
    total_bytes: Optional[float]
    speed: Optional[float]
    eta: Optional[float]
    quality_label: str


@dataclass
class VideoResult:
    index: int
    title: str
    success: bool
    skipped: bool = False
    error: Optional[str] = None
    output_path: Optional[Path] = None


@dataclass
class DownloadRunResult:
    downloaded: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[VideoResult] = field(default_factory=list)
    destination: Optional[Path] = None


ProgressCallback = Callable[[ProgressEvent], None]


# --------------------------------------------------------------------------
# Extraction (metadata only, no download)
# --------------------------------------------------------------------------

def extract_target(url: str, *, flat: bool = True) -> ExtractedTarget:
    """Fetch metadata for ``url`` without downloading anything.

    ``flat=True`` (the default) uses yt-dlp's flat playlist extraction,
    which is fast but leaves each playlist entry as a stub (formats
    unknown, and on some sites no direct video URL). Pass ``flat=False``
    to fully resolve every entry -- used as a fallback when a flat
    entry doesn't carry enough information to download it (see
    :func:`entry_download_url`).

    Raises a :class:`DownloadAppError` subclass on failure.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist" if flat else False,
        "skip_download": True,
        "logger": _SilentYtdlpLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise classify_ytdlp_error(exc) from exc
    except Exception as exc:  # noqa: BLE001 - translate anything unexpected
        raise classify_ytdlp_error(exc) from exc

    if info is None:
        raise URLUnavailableError("Could not retrieve any information for this URL.")

    if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        videos = [
            VideoInfo(
                id=e.get("id", ""),
                title=e.get("title") or "Untitled",
                uploader=e.get("uploader") or info.get("uploader") or "unknown",
                duration=e.get("duration"),
                raw=e,
            )
            for e in entries
        ]
        return ExtractedTarget(
            is_playlist=True,
            playlist_title=info.get("title"),
            videos=videos,
            formats=[],
            raw=info,
        )

    # Single video -- fetch full (non-flat) info so we get real formats.
    formats = info.get("formats") or []
    video = VideoInfo(
        id=info.get("id", ""),
        title=info.get("title") or "Untitled",
        uploader=info.get("uploader") or "unknown",
        duration=info.get("duration"),
        raw=info,
    )
    return ExtractedTarget(
        is_playlist=False,
        playlist_title=None,
        videos=[video],
        formats=formats,
        raw=info,
    )


def entry_download_url(entry: Dict[str, Any]) -> Optional[str]:
    """Extract a directly-downloadable URL from a (possibly flat) playlist entry.

    yt-dlp's flat playlist entries vary by site: most carry a full
    ``webpage_url``, some only a partial ``url`` (occasionally just an
    id fragment on obscure extractors), and ``original_url`` is a
    fallback some extractors set. This is deliberately site-agnostic --
    no per-site URL reconstruction (e.g. hand-building a YouTube watch
    URL from an id) -- because that only works for the one site it was
    written for.
    """
    for key in ("webpage_url", "url", "original_url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def fetch_formats_for_video(url: str) -> List[Dict[str, Any]]:
    """Fetch the full (non-flat) format list for a single video URL."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "logger": _SilentYtdlpLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise classify_ytdlp_error(exc) from exc
    return (info or {}).get("formats") or []


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------

class Downloader:
    """Configures and runs yt-dlp downloads for a video or playlist."""

    def __init__(
        self,
        destination: Path,
        quality: QualityChoice,
        filename_mode: str,
        filename_pattern: Optional[str],
        existing_file_behavior: str = "skip",
        progress_callback: Optional[ProgressCallback] = None,
        ask_overwrite_callback: Optional[Callable[[str], str]] = None,
        prefer_mp4: bool = True,
    ):
        self.destination = destination
        self.quality = quality
        self.filename_mode = filename_mode
        self.filename_pattern = filename_pattern
        self.existing_file_behavior = existing_file_behavior
        self.progress_callback = progress_callback
        self.ask_overwrite_callback = ask_overwrite_callback
        # Whether forcing a remux to .mp4 makes sense for what's being
        # downloaded. Callers with real formats up front (a single
        # video) should pass formats_support_mp4(formats); a webm/vp9
        # -only site shouldn't have mp4 forced on it. Defaults to True
        # (today's YouTube-shaped assumption) when the caller doesn't
        # know in advance (e.g. a playlist, whose per-item formats
        # aren't resolved until download time).
        self.prefer_mp4 = prefer_mp4

        if not self.quality.is_audio_only and not ffmpeg_available():
            # We don't hard-fail here because many single-quality
            # "progressive" streams don't need merging -- yt-dlp will
            # raise its own FFmpeg-related error at download time if a
            # merge actually turns out to be necessary, and we translate
            # that via classify_ytdlp_error. We just warn upfront.
            logger.info("FFmpeg not found on PATH -- merges will fail if needed.")

    def _video_index_to_stem(self, index: int, metadata: Dict[str, Any]) -> str:
        return build_filename(
            mode=self.filename_mode,
            index=index,
            metadata=metadata,
            pattern=self.filename_pattern,
        )

    def _make_progress_hook(self, video_index: int, video_total: int, title: str):
        def hook(d: Dict[str, Any]) -> None:
            if not self.progress_callback:
                return
            status = d.get("status")
            if status == "downloading":
                event = ProgressEvent(
                    status="downloading",
                    video_index=video_index,
                    video_total=video_total,
                    title=title,
                    downloaded_bytes=d.get("downloaded_bytes"),
                    total_bytes=d.get("total_bytes") or d.get("total_bytes_estimate"),
                    speed=d.get("speed"),
                    eta=d.get("eta"),
                    quality_label=self.quality.label,
                )
                self.progress_callback(event)
            elif status == "finished":
                event = ProgressEvent(
                    status="finished",
                    video_index=video_index,
                    video_total=video_total,
                    title=title,
                    downloaded_bytes=d.get("downloaded_bytes"),
                    total_bytes=d.get("total_bytes"),
                    speed=None,
                    eta=0,
                    quality_label=self.quality.label,
                )
                self.progress_callback(event)

        return hook

    def _build_ydl_opts(self, stem_path: Path, video_index: int, video_total: int, title: str) -> Dict[str, Any]:
        outtmpl = f"{stem_path}.%(ext)s"

        opts: Dict[str, Any] = {
            "format": build_format_selector(self.quality),
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _SilentYtdlpLogger(),
            "continuedl": True,  # resume partial downloads
            "retries": 5,
            "fragment_retries": 5,
            "progress_hooks": [self._make_progress_hook(video_index, video_total, title)],
            "noplaylist": True,  # we drive playlist iteration ourselves
            # A preference list, not a hard requirement (yt-dlp picks the
            # first one whose codecs actually fit -- see
            # get_compatible_ext): falls back to mkv rather than forcing
            # an incompatible mp4 mux when the codecs don't fit it.
            "merge_output_format": "mp4/mkv",
        }

        if self.quality.is_audio_only:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        elif self.prefer_mp4:
            # Force a remux to mp4 only when the site's codecs are known
            # to fit it -- this is a no-op stream-copy if the merge/
            # download already produced mp4, but on a webm/vp9-only site
            # it would otherwise force a lossy or failing conversion.
            opts["postprocessors"] = [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ]

        return opts

    def download_one(
        self, url: Optional[str], index: int, video_total: int, metadata: Dict[str, Any]
    ) -> VideoResult:
        """Download a single video (by URL) to its computed target path."""
        title = metadata.get("title") or "Untitled"

        if not url:
            logger.error("No direct URL available for item %d (%s)", index, title)
            return VideoResult(
                index=index,
                title=title,
                success=False,
                error="This site did not provide a direct link for this item.",
            )

        stem = self._video_index_to_stem(index, metadata)
        stem_path = self.destination / stem

        existing = existing_outputs(self.destination, stem)
        if existing:
            behavior = self.existing_file_behavior
            if behavior == "ask" and self.ask_overwrite_callback:
                behavior = self.ask_overwrite_callback(str(existing[0]))
            if behavior == "skip":
                logger.info("Skipping existing file: %s", existing[0])
                return VideoResult(index=index, title=title, success=True, skipped=True, output_path=existing[0])
            if behavior == "overwrite":
                for path in existing:
                    try:
                        path.unlink()
                    except OSError:
                        pass
            # "overwrite" falls through to a normal download below.
            # Any other behavior value also falls through defensively.

        ydl_opts = self._build_ydl_opts(stem_path, index, video_total, title)

        # The real output extension depends on the site's actual codecs
        # (mp4, webm, mkv, mp3, ...) -- post_hooks fires with the final
        # path after all postprocessing, so this is the authoritative
        # way to learn it rather than assuming .mp4/.mp3.
        captured_paths: List[Path] = []
        ydl_opts["post_hooks"] = [lambda path: captured_paths.append(Path(path))]

        logger.info(
            "Starting download | url=%s | quality=%s | destination=%s | filename=%s",
            url, self.quality.label, self.destination, stem,
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            friendly = classify_ytdlp_error(exc)
            logger.error("Download failed | url=%s | reason=%s", url, friendly)
            return VideoResult(index=index, title=title, success=False, error=str(friendly))
        except OSError as exc:
            friendly = classify_ytdlp_error(exc)
            logger.error("Download failed (OS error) | url=%s | reason=%s", url, friendly)
            return VideoResult(index=index, title=title, success=False, error=str(friendly))

        output_path = captured_paths[-1] if captured_paths else stem_path
        logger.info("Download succeeded | url=%s | file=%s", url, output_path.name)
        return VideoResult(index=index, title=title, success=True, output_path=output_path)

    def download_many(
        self,
        video_urls: List[Optional[str]],
        metadatas: List[Dict[str, Any]],
        stop_on_first_failure: bool = False,
    ) -> DownloadRunResult:
        """Download a sequence of videos (used for playlists).

        A failure on one item does not stop the rest unless
        ``stop_on_first_failure`` is True.
        """
        run_result = DownloadRunResult(destination=self.destination)
        total = len(video_urls)

        for i, (url, meta) in enumerate(zip(video_urls, metadatas), start=1):
            result = self.download_one(url, i, total, meta)
            run_result.results.append(result)
            if result.skipped:
                run_result.skipped += 1
            elif result.success:
                run_result.downloaded += 1
            else:
                run_result.failed += 1
                if stop_on_first_failure:
                    break

        return run_result
