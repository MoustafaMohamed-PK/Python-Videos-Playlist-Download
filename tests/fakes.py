"""
Hand-written test doubles for app.service, in place of network mocks.

Responsible for:
    - FakeExtractor: a drop-in replacement for app.downloader.extract_target
      that returns pre-built ExtractedTarget objects instead of hitting
      yt-dlp/the network.
    - fake_formats_fetcher: a drop-in replacement for fetch_formats_for_video.
    - FakeDownloader: a drop-in replacement for app.downloader.Downloader
      that writes real (empty) files to a real temp directory and emits
      scripted ProgressEvents, instead of calling yt-dlp.

These let app.service (and anything built on it) be tested end-to-end
-- including real filesystem effects like the existing-file skip check
-- without touching the network, while keeping the rest of the suite's
"real objects over mocks" style intact. See tests/test_service.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.downloader import DownloadRunResult, ExtractedTarget, ProgressEvent, VideoResult


class FakeExtractor:
    """Callable replacement for extract_target that returns canned targets.

    Construct with one ExtractedTarget (returned regardless of flat=)
    or a list of them (returned in call order, for tests that need the
    flat-then-full-reextraction fallback path in
    app.service._resolve_playlist_urls).
    """

    def __init__(self, targets):
        self._targets = targets if isinstance(targets, list) else [targets]
        self._index = 0
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, url: str, *, flat: bool = True) -> ExtractedTarget:
        self.calls.append({"url": url, "flat": flat})
        target = self._targets[min(self._index, len(self._targets) - 1)]
        self._index += 1
        return target


def fake_formats_fetcher(formats: List[Dict[str, Any]]) -> Callable[[str], List[Dict[str, Any]]]:
    """Build a fetch_formats_for_video replacement returning a fixed list."""

    def _fetch(url: str) -> List[Dict[str, Any]]:
        return formats

    return _fetch


class FakeDownloader:
    """Callable-as-a-class replacement for app.downloader.Downloader.

    Writes a real (empty) file per item into ``destination`` and
    returns a successful VideoResult for each, emitting scripted
    ProgressEvents through the real progress_callback contract. Doesn't
    touch the network or require ffmpeg/yt-dlp.
    """

    def __init__(
        self,
        destination: Path,
        quality,
        filename_mode: str,
        filename_pattern: Optional[str],
        existing_file_behavior: str = "skip",
        progress_callback=None,
        ask_overwrite_callback=None,
        prefer_mp4: bool = True,
    ):
        self.destination = destination
        self.quality = quality
        self.filename_mode = filename_mode
        self.filename_pattern = filename_pattern
        self.existing_file_behavior = existing_file_behavior
        self.progress_callback = progress_callback
        self.ask_overwrite_callback = ask_overwrite_callback
        self.prefer_mp4 = prefer_mp4

    def download_many(
        self,
        video_urls: List[Optional[str]],
        metadatas: List[Dict[str, Any]],
        stop_on_first_failure: bool = False,
    ) -> DownloadRunResult:
        self.destination.mkdir(parents=True, exist_ok=True)
        run_result = DownloadRunResult(destination=self.destination)

        for i, (url, meta) in enumerate(zip(video_urls, metadatas), start=1):
            title = meta.get("title") or "Untitled"
            if not url:
                run_result.results.append(
                    VideoResult(index=i, title=title, success=False, error="No URL")
                )
                run_result.failed += 1
                continue

            if self.progress_callback:
                self.progress_callback(
                    ProgressEvent(
                        status="downloading",
                        video_index=i,
                        video_total=len(video_urls),
                        title=title,
                        downloaded_bytes=50,
                        total_bytes=100,
                        speed=1000,
                        eta=1,
                        quality_label=self.quality.label,
                    )
                )

            ext = "mp3" if self.quality.is_audio_only else "mp4"
            output_path = self.destination / f"{title}.{ext}"
            output_path.write_bytes(b"fake media content")

            if self.progress_callback:
                self.progress_callback(
                    ProgressEvent(
                        status="finished",
                        video_index=i,
                        video_total=len(video_urls),
                        title=title,
                        downloaded_bytes=100,
                        total_bytes=100,
                        speed=None,
                        eta=0,
                        quality_label=self.quality.label,
                    )
                )

            run_result.results.append(
                VideoResult(index=i, title=title, success=True, output_path=output_path)
            )
            run_result.downloaded += 1

        return run_result
