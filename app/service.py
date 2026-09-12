"""
Shared download logic, with zero terminal I/O.

Responsible for:
    - analyze(): validate + extract metadata for a URL, resolve the
      per-item download URLs, and build a quality menu -- everything a
      caller needs to know about a URL before deciding how to download
      it.
    - plan(): turn a user's requested settings (quality/destination/
      naming/etc.) plus an AnalyzeResult into a concrete, validated
      RunPlan, raising a typed error with the real menu attached if the
      requested quality doesn't exist.
    - execute(): run a RunPlan through the Downloader and return the
      result.

This module is the single place both the interactive CLI and the
non-interactive CLI call into, so they can never drift -- and it's
where a future web UI hooks in too. Nothing here calls ``print`` or
``input()``, and every network-touching function takes its
dependencies as injectable keyword defaults so it can be tested without
hitting the network (see tests/fakes.py).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.downloader import (
    DownloadAppError,
    Downloader,
    DownloadRunResult,
    ExtractedTarget,
    ProgressCallback,
    VideoInfo,
    entry_download_url,
    extract_target,
    fetch_formats_for_video,
)
from app.formats import (
    QUALITY_LADDER,
    QualityChoice,
    QualityOption,
    build_quality_menu,
    formats_support_mp4,
    quality_is_available,
)
from app.sites import validate_media_url

Extractor = Callable[..., ExtractedTarget]
FormatsFetcher = Callable[[str], List[Dict[str, Any]]]
DownloaderFactory = Callable[..., Downloader]


class QualityUnavailableError(DownloadAppError):
    """The requested quality isn't among the video's real formats.

    Carries the real menu (``menu``) so a caller can show the user what
    *is* available without having to recompute it.
    """

    def __init__(self, message: str, menu: List[QualityOption]):
        super().__init__(message)
        self.menu = menu


@dataclass
class AnalyzeResult:
    """Everything known about a URL before deciding how to download it."""

    url: str
    is_playlist: bool
    playlist_title: Optional[str]
    title: str
    videos: List[VideoInfo]
    formats: List[Dict[str, Any]]  # only populated for a single video
    quality_menu: List[QualityOption]
    video_urls: List[Optional[str]]  # resolved per-item download URLs
    warnings: List[str] = field(default_factory=list)


@dataclass
class DownloadRequest:
    """User-requested settings for a download, independent of the target."""

    quality_label: str
    destination: Path
    filename_mode: str
    filename_pattern: Optional[str]
    existing_file_behavior: str = "skip"
    concurrency: int = 1  # playlist items downloaded in parallel
    concurrent_fragments: int = 4  # yt-dlp's own per-item fragment parallelism


@dataclass
class RunPlan:
    """A validated, ready-to-execute download plan."""

    quality: QualityChoice
    destination: Path
    filename_mode: str
    filename_pattern: Optional[str]
    existing_file_behavior: str
    prefer_mp4: bool
    video_urls: List[Optional[str]]
    metadatas: List[Dict[str, Any]]
    title: str
    is_playlist: bool
    video_count: int
    concurrency: int
    concurrent_fragments: int


def _ladder_menu() -> List[QualityOption]:
    """The fixed QUALITY_LADDER rendered as a QualityOption menu.

    Used for playlists, where formats aren't known upfront (yt-dlp's
    flat playlist extraction doesn't resolve each entry's formats) --
    unlike a single video, there's no real format list to build a menu
    from yet, so this is the best available approximation up front.
    """
    return [
        QualityOption(key=label, label=display, height=QualityChoice(label=label).height)
        for label, display in QUALITY_LADDER
    ]


def _resolve_playlist_urls(
    url: str, target: ExtractedTarget, extractor: Extractor
) -> List[Optional[str]]:
    """Compute the per-video download URL list for a playlist.

    yt-dlp's flat extraction gives each entry a direct URL on most
    sites (``webpage_url``/``url``/``original_url``, via
    :func:`app.downloader.entry_download_url`, which is site-agnostic --
    no per-site URL reconstruction). A handful of extractors don't put
    a direct URL on the flat entry at all; when that happens, re-extract
    the playlist fully (non-flat) once and use those URLs instead. Any
    entry still missing a URL after that is reported as ``None`` and
    fails individually at download time rather than being silently
    skipped or guessed at.
    """
    urls: List[Optional[str]] = [entry_download_url(video.raw) for video in target.videos]
    if None not in urls:
        return urls

    try:
        full_target = extractor(url, flat=False)
    except DownloadAppError:
        return urls

    full_urls = [entry_download_url(video.raw) for video in full_target.videos]
    if len(full_urls) != len(urls):
        return urls
    return [full or flat for full, flat in zip(full_urls, urls)]


def analyze(
    url: str,
    *,
    extractor: Extractor = extract_target,
    formats_fetcher: FormatsFetcher = fetch_formats_for_video,
) -> AnalyzeResult:
    """Validate ``url`` and fetch everything needed to plan a download.

    Raises :class:`app.validators.ValidationError` (including its
    subclass :class:`app.sites.UnsupportedSiteError`) if ``url`` is
    malformed or unsupported, or a :class:`DownloadAppError` subclass
    if extraction itself fails. Callers must catch both.
    """
    validated_url = validate_media_url(url)
    target = extractor(validated_url)

    if target.is_playlist:
        formats: List[Dict[str, Any]] = []
        quality_menu = _ladder_menu()
        video_urls = _resolve_playlist_urls(validated_url, target, extractor)
    else:
        formats = target.formats or formats_fetcher(validated_url)
        quality_menu = build_quality_menu(formats)
        video_urls = [validated_url]

    if target.is_playlist:
        title = target.playlist_title or "Untitled playlist"
    else:
        title = target.videos[0].title if target.videos else "Untitled"

    return AnalyzeResult(
        url=validated_url,
        is_playlist=target.is_playlist,
        playlist_title=target.playlist_title,
        title=title,
        videos=target.videos,
        formats=formats,
        quality_menu=quality_menu,
        video_urls=video_urls,
    )


def plan(request: DownloadRequest, analysis: AnalyzeResult) -> RunPlan:
    """Turn a :class:`DownloadRequest` plus an :class:`AnalyzeResult` into a RunPlan.

    Raises :class:`QualityUnavailableError` (carrying the real menu) if
    the requested quality doesn't exist for a single video. Playlists
    aren't validated here -- their per-item formats aren't known until
    each item downloads, so a per-item request instead relies on
    app/formats.py's height<= selector fallback tiers to get as close
    as possible to what was asked for.
    """
    quality = QualityChoice(label=request.quality_label)

    # Whether forcing a remux to mp4 makes sense. Known up front for a
    # single video (real formats are available); for a playlist,
    # per-item formats aren't resolved until download time, so keep
    # today's YouTube-shaped default.
    prefer_mp4 = True

    if not analysis.is_playlist:
        if not quality_is_available(quality, analysis.formats):
            raise QualityUnavailableError(
                f"The selected {request.quality_label} quality is not available for this video.",
                menu=analysis.quality_menu,
            )
        prefer_mp4 = formats_support_mp4(analysis.formats)

    metadatas = [{"title": v.title, "uploader": v.uploader} for v in analysis.videos]

    return RunPlan(
        quality=quality,
        destination=request.destination,
        filename_mode=request.filename_mode,
        filename_pattern=request.filename_pattern,
        existing_file_behavior=request.existing_file_behavior,
        prefer_mp4=prefer_mp4,
        video_urls=analysis.video_urls,
        metadatas=metadatas,
        title=analysis.title,
        is_playlist=analysis.is_playlist,
        video_count=len(analysis.videos),
        # "concurrency" means playlist items in parallel; a single video
        # is always exactly one item, so force it to 1 regardless of
        # what was requested rather than spinning up an unused thread
        # pool for it.
        concurrency=max(1, min(8, request.concurrency)) if analysis.is_playlist else 1,
        concurrent_fragments=max(1, min(8, request.concurrent_fragments)),
    )


def execute(
    run_plan: RunPlan,
    *,
    progress_callback: Optional[ProgressCallback] = None,
    ask_overwrite_callback: Optional[Callable[[str], str]] = None,
    cancel_event: Optional[threading.Event] = None,
    downloader_factory: DownloaderFactory = Downloader,
) -> DownloadRunResult:
    """Run a validated :class:`RunPlan` and return the result."""
    downloader = downloader_factory(
        destination=run_plan.destination,
        quality=run_plan.quality,
        filename_mode=run_plan.filename_mode,
        filename_pattern=run_plan.filename_pattern,
        existing_file_behavior=run_plan.existing_file_behavior,
        progress_callback=progress_callback,
        ask_overwrite_callback=ask_overwrite_callback,
        prefer_mp4=run_plan.prefer_mp4,
        concurrent_fragments=run_plan.concurrent_fragments,
        cancel_event=cancel_event,
    )
    return downloader.download_many(
        run_plan.video_urls, run_plan.metadatas, concurrency=run_plan.concurrency
    )
