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

import time
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
        concurrent_fragments: int = 4,
        cancel_event=None,
        subtitle_langs=None,
        subtitles_only: bool = False,
        delay: float = 0.0,
        conflict_indices: frozenset = frozenset(),
    ):
        self.destination = destination
        self.quality = quality
        self.filename_mode = filename_mode
        self.filename_pattern = filename_pattern
        self.existing_file_behavior = existing_file_behavior
        self.progress_callback = progress_callback
        self.ask_overwrite_callback = ask_overwrite_callback
        self.prefer_mp4 = prefer_mp4
        self.concurrent_fragments = concurrent_fragments
        self.cancel_event = cancel_event
        self.subtitle_langs = subtitle_langs or []
        self.subtitles_only = subtitles_only
        # Artificial per-item delay, purely for tests that need to
        # observe an in-progress state (job manager cancellation,
        # snapshot polling) instead of a job that finishes instantly.
        self.delay = delay
        # 1-based item indices to simulate as "target file already
        # exists" -- exercises the same existing_file_behavior /
        # ask_overwrite_callback contract as the real Downloader,
        # without needing a real pre-existing file on disk.
        self.conflict_indices = conflict_indices

    def download_many(
        self,
        video_urls: List[Optional[str]],
        metadatas: List[Dict[str, Any]],
        stop_on_first_failure: bool = False,
        concurrency: int = 1,
    ) -> DownloadRunResult:
        self.destination.mkdir(parents=True, exist_ok=True)
        run_result = DownloadRunResult(destination=self.destination)

        for i, (url, meta) in enumerate(zip(video_urls, metadatas), start=1):
            if self.cancel_event is not None and self.cancel_event.is_set():
                break

            title = meta.get("title") or "Untitled"
            if not url:
                run_result.results.append(
                    VideoResult(index=i, title=title, success=False, error="No URL")
                )
                run_result.failed += 1
                continue

            if i in self.conflict_indices:
                fake_existing_path = self.destination / f"{title}.mp4"
                behavior = self.existing_file_behavior
                if behavior == "ask" and self.ask_overwrite_callback:
                    behavior = self.ask_overwrite_callback(str(fake_existing_path))
                if behavior == "skip":
                    run_result.results.append(
                        VideoResult(
                            index=i, title=title, success=True, skipped=True,
                            output_path=fake_existing_path,
                        )
                    )
                    run_result.skipped += 1
                    continue
                # "overwrite" (or any other value, defensively) falls
                # through to a normal download below, same as the real
                # Downloader.

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

            if self.delay:
                time.sleep(self.delay)

            for lang in self.subtitle_langs:
                (self.destination / f"{title}.{lang}.srt").write_bytes(b"fake subtitle content")

            if self.subtitles_only:
                if not self.subtitle_langs:
                    run_result.results.append(
                        VideoResult(index=i, title=title, success=False, error="No subtitles were found.")
                    )
                    run_result.failed += 1
                    continue
                output_path = self.destination / f"{title}.{self.subtitle_langs[0]}.srt"
            else:
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
