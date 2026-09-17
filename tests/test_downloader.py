import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yt_dlp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.downloader import Downloader, VideoResult
from app.formats import QualityChoice


class _FakeWorkDownloader(Downloader):
    """Downloader subclass with download_one faked out.

    Tests download_many's orchestration (ordering, concurrency,
    cancellation) without touching yt-dlp or the network -- the thing
    actually under test here is the ThreadPoolExecutor wiring in
    app/downloader.py, not yt-dlp itself.
    """

    def __init__(self, *args, delay: float = 0.05, fail_indices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.delay = delay
        self.fail_indices = set(fail_indices)
        self.active = 0
        self.max_active = 0
        self.started_order = []
        self._lock = threading.Lock()

    def download_one(self, url, index, video_total, metadata, playlist_position=None):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.started_order.append(index)
        time.sleep(self.delay)
        with self._lock:
            self.active -= 1

        title = metadata.get("title", "")
        if index in self.fail_indices:
            return VideoResult(index=index, title=title, success=False, error="boom")
        return VideoResult(index=index, title=title, success=True, output_path=Path(f"/tmp/item{index}"))


def _make_downloader(cls=_FakeWorkDownloader, **kwargs):
    return cls(
        destination=Path("/tmp/ytdl_test_downloader"),
        quality=QualityChoice(label="best"),
        filename_mode="original",
        filename_pattern=None,
        **kwargs,
    )


class TestDownloadManySequential(unittest.TestCase):
    def test_downloads_in_order_one_at_a_time(self):
        d = _make_downloader(delay=0.02)
        urls = [f"https://example.com/{i}" for i in range(1, 6)]
        metas = [{"title": f"Item {i}"} for i in range(1, 6)]

        result = d.download_many(urls, metas, concurrency=1)

        self.assertEqual(d.max_active, 1)
        self.assertEqual(d.started_order, [1, 2, 3, 4, 5])
        self.assertEqual([r.index for r in result.results], [1, 2, 3, 4, 5])
        self.assertEqual(result.downloaded, 5)

    def test_stop_on_first_failure_halts_remaining_items(self):
        d = _make_downloader(delay=0.01, fail_indices={2})
        urls = [f"https://example.com/{i}" for i in range(1, 6)]
        metas = [{"title": f"Item {i}"} for i in range(1, 6)]

        result = d.download_many(urls, metas, concurrency=1, stop_on_first_failure=True)

        self.assertEqual([r.index for r in result.results], [1, 2])
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.downloaded, 1)


class TestDownloadManyConcurrent(unittest.TestCase):
    def test_items_run_in_parallel(self):
        d = _make_downloader(delay=0.1)
        urls = [f"https://example.com/{i}" for i in range(1, 6)]
        metas = [{"title": f"Item {i}"} for i in range(1, 6)]

        result = d.download_many(urls, metas, concurrency=3)

        self.assertGreater(d.max_active, 1)
        self.assertLessEqual(d.max_active, 3)
        self.assertEqual(result.downloaded, 5)

    def test_results_are_returned_in_original_order_regardless_of_completion_order(self):
        # Later-indexed items finish first (shorter delay) to prove
        # ordering comes from a post-hoc sort, not completion order.
        d = _make_downloader(delay=0.0)
        d.download_one = lambda url, index, total, meta, playlist_position=None: (
            time.sleep(0.05 / index),  # higher index finishes sooner
            VideoResult(index=index, title="", success=True),
        )[1]
        urls = [f"https://example.com/{i}" for i in range(1, 6)]
        metas = [{"title": f"Item {i}"} for i in range(1, 6)]

        result = d.download_many(urls, metas, concurrency=5)

        self.assertEqual([r.index for r in result.results], [1, 2, 3, 4, 5])

    def test_stop_on_first_failure_sets_cancel_event(self):
        cancel_event = threading.Event()
        d = _make_downloader(delay=0.02, fail_indices={1}, cancel_event=cancel_event)
        urls = [f"https://example.com/{i}" for i in range(1, 4)]
        metas = [{"title": f"Item {i}"} for i in range(1, 4)]

        d.download_many(urls, metas, concurrency=3, stop_on_first_failure=True)

        self.assertTrue(cancel_event.is_set())

    def test_preset_cancel_event_skips_all_items(self):
        cancel_event = threading.Event()
        cancel_event.set()
        d = _make_downloader(cancel_event=cancel_event)
        urls = [f"https://example.com/{i}" for i in range(1, 4)]
        metas = [{"title": f"Item {i}"} for i in range(1, 4)]

        result = d.download_many(urls, metas, concurrency=3)

        self.assertEqual(result.results, [])
        self.assertEqual(d.started_order, [])


class TestProgressHookCancellation(unittest.TestCase):
    def test_hook_raises_download_cancelled_when_event_is_set(self):
        cancel_event = threading.Event()
        cancel_event.set()
        d = _make_downloader(cls=Downloader, cancel_event=cancel_event)
        hook = d._make_progress_hook(1, 1, "Title")
        with self.assertRaises(yt_dlp.utils.DownloadCancelled):
            hook({"status": "downloading"})

    def test_hook_does_not_raise_when_no_cancel_event(self):
        d = _make_downloader(cls=Downloader)
        hook = d._make_progress_hook(1, 1, "Title")
        hook({"status": "downloading"})  # must not raise


class TestDownloadOneErrorClassification(unittest.TestCase):
    """The one place mocking yt_dlp.YoutubeDL directly is justified:
    verifying download_one translates a raw yt-dlp DownloadError into
    the app's friendly, typed error message -- this is the only path
    that actually needs a real yt-dlp exception shape, which nothing
    else in the fixture-based test suite can produce without a real
    network call.
    """

    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_private_video_error_is_classified(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.download.side_effect = yt_dlp.utils.DownloadError(
            "ERROR: Private video. Sign in if you've been granted access to this video"
        )
        mock_ydl_cls.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            d = _make_downloader(cls=Downloader)
            d.destination = Path(tmp)
            result = d.download_one("https://example.com/v", 1, 1, {"title": "T"})

        self.assertFalse(result.success)
        self.assertIn("private", result.error.lower())

    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_ffmpeg_missing_error_is_classified(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.download.side_effect = yt_dlp.utils.DownloadError(
            "ERROR: ffmpeg not found. Please install"
        )
        mock_ydl_cls.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            d = _make_downloader(cls=Downloader)
            d.destination = Path(tmp)
            result = d.download_one("https://example.com/v", 1, 1, {"title": "T"})

        self.assertFalse(result.success)
        self.assertIn("ffmpeg", result.error.lower())


class TestBuildYdlOptsSubtitles(unittest.TestCase):
    def test_no_subtitles_requested_omits_subtitle_opts(self):
        d = _make_downloader(cls=Downloader)
        opts = d._build_ydl_opts(Path("/tmp/stem"), 1, 1, "Title")
        self.assertNotIn("writesubtitles", opts)
        self.assertIn("format", opts)

    def test_subtitle_langs_sets_write_flags(self):
        d = _make_downloader(cls=Downloader, subtitle_langs=["en", "es"])
        opts = d._build_ydl_opts(Path("/tmp/stem"), 1, 1, "Title")
        self.assertTrue(opts["writesubtitles"])
        self.assertTrue(opts["writeautomaticsub"])
        self.assertEqual(opts["subtitleslangs"], ["en", "es"])
        # Still downloads video/audio -- subtitles_only wasn't set.
        self.assertIn("format", opts)

    def test_playlist_position_selects_that_item_and_clears_noplaylist(self):
        # Sites that put several videos behind one URL (an Instagram
        # carousel post) can only be addressed by position, and
        # "noplaylist" would override that and take the first video.
        d = _make_downloader(cls=Downloader)
        opts = d._build_ydl_opts(Path("/tmp/stem"), 2, 3, "Title", playlist_position=2)
        self.assertEqual(opts["playlist_items"], "2")
        self.assertFalse(opts["noplaylist"])

    def test_without_playlist_position_noplaylist_stays_on(self):
        d = _make_downloader(cls=Downloader)
        opts = d._build_ydl_opts(Path("/tmp/stem"), 1, 1, "Title")
        self.assertTrue(opts["noplaylist"])
        self.assertNotIn("playlist_items", opts)

    def test_subtitles_only_skips_download_and_omits_format(self):
        d = _make_downloader(cls=Downloader, subtitle_langs=["en"], subtitles_only=True)
        opts = d._build_ydl_opts(Path("/tmp/stem"), 1, 1, "Title")
        self.assertTrue(opts["skip_download"])
        self.assertNotIn("format", opts)
        self.assertNotIn("merge_output_format", opts)

    def test_subtitles_only_ignores_audio_extraction_postprocessor(self):
        d = Downloader(
            destination=Path("/tmp/ytdl_test_downloader"),
            quality=QualityChoice(label="audio"),
            filename_mode="original",
            filename_pattern=None,
            subtitle_langs=["en"],
            subtitles_only=True,
        )
        opts = d._build_ydl_opts(Path("/tmp/stem"), 1, 1, "Title")
        keys = [pp["key"] for pp in opts.get("postprocessors", [])]
        self.assertNotIn("FFmpegExtractAudio", keys)


class TestSubtitleFetchRetry(unittest.TestCase):
    """A subtitle fetch failure for one language (e.g. a rate limit)
    aborts yt-dlp's entire download -- video included, since subtitles
    are fetched before the media file. download_one must retry without
    the failing language rather than losing the whole item.
    """

    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_retries_without_failing_language_and_succeeds(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_ydl_cls.return_value = mock_instance

        calls = {"n": 0}

        def fake_download(urls):
            calls["n"] += 1
            if calls["n"] == 1:
                raise yt_dlp.utils.DownloadError(
                    "Unable to download video subtitles for 'ar': HTTP Error 429: Too Many Requests"
                )

        mock_instance.download.side_effect = fake_download

        with tempfile.TemporaryDirectory() as tmp:
            d = _make_downloader(cls=Downloader, subtitle_langs=["en", "ar"])
            d.destination = Path(tmp)
            result = d.download_one("https://example.com/v", 1, 1, {"title": "Title"})

        self.assertTrue(result.success)
        self.assertEqual(calls["n"], 2)
        self.assertIn("ar", result.warning)

        second_call_opts = mock_ydl_cls.call_args_list[1].args[0]
        self.assertEqual(second_call_opts["subtitleslangs"], ["en"])

    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_unrelated_download_error_is_not_retried(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.download.side_effect = yt_dlp.utils.DownloadError(
            "ERROR: Private video. Sign in if you've been granted access to this video"
        )
        mock_ydl_cls.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            d = _make_downloader(cls=Downloader, subtitle_langs=["en"])
            d.destination = Path(tmp)
            result = d.download_one("https://example.com/v", 1, 1, {"title": "Title"})

        self.assertFalse(result.success)
        self.assertEqual(mock_instance.download.call_count, 1)
        self.assertIn("private", result.error.lower())

    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_no_subtitles_requested_never_enters_retry_path(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.download.return_value = None
        mock_ydl_cls.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            d = _make_downloader(cls=Downloader)
            d.destination = Path(tmp)
            result = d.download_one("https://example.com/v", 1, 1, {"title": "Title"})

        self.assertTrue(result.success)
        self.assertIsNone(result.warning)
        self.assertEqual(mock_instance.download.call_count, 1)


class TestDownloadOneSubtitlesOnly(unittest.TestCase):
    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_success_when_subtitle_file_lands_on_disk(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_ydl_cls.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            d = _make_downloader(cls=Downloader, subtitle_langs=["en"], subtitles_only=True)
            d.destination = destination

            def fake_download(urls):
                (destination / "Title.en.srt").write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nHi\n")

            mock_instance.download.side_effect = fake_download

            result = d.download_one("https://example.com/v", 1, 1, {"title": "Title"})

        self.assertTrue(result.success)
        self.assertEqual(result.output_path.name, "Title.en.srt")

    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_failure_when_no_subtitle_file_produced(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.download.return_value = None
        mock_ydl_cls.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            d = _make_downloader(cls=Downloader, subtitle_langs=["en"], subtitles_only=True)
            d.destination = Path(tmp)
            result = d.download_one("https://example.com/v", 1, 1, {"title": "Title"})

        self.assertFalse(result.success)
        self.assertIn("no subtitles", result.error.lower())


if __name__ == "__main__":
    unittest.main()
