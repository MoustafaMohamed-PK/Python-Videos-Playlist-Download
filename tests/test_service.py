import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.downloader import ExtractedTarget, VideoInfo
from app.formats import QualityChoice
from app.service import DownloadRequest, QualityUnavailableError, analyze, execute, plan
from app.validators import ValidationError
from tests.fakes import FakeDownloader, FakeExtractor, fake_formats_fetcher

# A real, offline-detectable URL (validate_media_url's extractor
# matching is pure regex against yt-dlp's bundled patterns -- no
# network involved) so analyze() can be exercised end-to-end with only
# the extraction step faked out.
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLxxxx"

SAMPLE_FORMATS = [
    {"format_id": "137", "height": 1080, "vcodec": "avc1", "acodec": "none"},
    {"format_id": "18", "height": 360, "vcodec": "avc1", "acodec": "mp4a"},
]

WEBM_ONLY_FORMATS = [
    {"format_id": "0", "height": 540, "vcodec": "vp9", "acodec": "none"},
    {"format_id": "1", "height": None, "vcodec": "none", "acodec": "opus"},
]


def _single_video_target(formats=SAMPLE_FORMATS) -> ExtractedTarget:
    return ExtractedTarget(
        is_playlist=False,
        playlist_title=None,
        videos=[VideoInfo(id="dQw4w9WgXcQ", title="Test Video", uploader="ChannelX")],
        formats=formats,
    )


def _playlist_target(entry_raws) -> ExtractedTarget:
    videos = [
        VideoInfo(id=f"id{i}", title=f"Item {i}", uploader="ChannelX", raw=raw)
        for i, raw in enumerate(entry_raws, start=1)
    ]
    return ExtractedTarget(is_playlist=True, playlist_title="My Playlist", videos=videos, formats=[])


class TestAnalyze(unittest.TestCase):
    def test_single_video_builds_menu_from_real_formats(self):
        result = analyze(YOUTUBE_URL, extractor=FakeExtractor(_single_video_target()))
        self.assertFalse(result.is_playlist)
        self.assertEqual(result.title, "Test Video")
        self.assertEqual(result.video_urls, [YOUTUBE_URL])
        self.assertEqual([o.key for o in result.quality_menu], ["best", "1080p", "360p"])

    def test_single_video_falls_back_to_formats_fetcher_when_flat(self):
        # extract_target returns formats=[] for a video extracted flat
        # (shouldn't normally happen for a single video, but analyze()
        # must not crash if it does) -- formats_fetcher covers it.
        target = _single_video_target(formats=[])
        result = analyze(
            YOUTUBE_URL,
            extractor=FakeExtractor(target),
            formats_fetcher=fake_formats_fetcher(SAMPLE_FORMATS),
        )
        self.assertEqual([o.key for o in result.quality_menu], ["best", "1080p", "360p"])

    def test_playlist_uses_fixed_ladder_menu(self):
        target = _playlist_target([{"webpage_url": "https://example.com/1"}])
        result = analyze(PLAYLIST_URL, extractor=FakeExtractor(target))
        self.assertTrue(result.is_playlist)
        self.assertIn("best", [o.key for o in result.quality_menu])
        self.assertIn("audio", [o.key for o in result.quality_menu])

    def test_playlist_resolves_direct_entry_urls(self):
        target = _playlist_target(
            [{"webpage_url": "https://example.com/1"}, {"url": "https://example.com/2"}]
        )
        result = analyze(PLAYLIST_URL, extractor=FakeExtractor(target))
        self.assertEqual(result.video_urls, ["https://example.com/1", "https://example.com/2"])

    def test_playlist_falls_back_to_full_reextraction_when_url_missing(self):
        flat_target = _playlist_target([{}])  # no direct URL on the flat entry
        full_target = _playlist_target([{"webpage_url": "https://example.com/resolved"}])
        extractor = FakeExtractor([flat_target, full_target])

        result = analyze(PLAYLIST_URL, extractor=extractor)

        self.assertEqual(result.video_urls, ["https://example.com/resolved"])
        # First call flat (default), second call explicitly non-flat.
        self.assertEqual([c["flat"] for c in extractor.calls], [True, False])

    def test_playlist_entry_still_missing_url_reports_none(self):
        flat_target = _playlist_target([{}])
        full_target = _playlist_target([{}])  # still no URL after full re-extraction
        extractor = FakeExtractor([flat_target, full_target])

        result = analyze(PLAYLIST_URL, extractor=extractor)

        self.assertEqual(result.video_urls, [None])

    def test_invalid_url_raises_before_extracting(self):
        extractor = FakeExtractor(_single_video_target())
        with self.assertRaises(ValidationError):
            analyze("not a url", extractor=extractor)
        self.assertEqual(extractor.calls, [])  # never reached extraction


class TestPlan(unittest.TestCase):
    def test_available_quality_produces_run_plan(self):
        analysis = analyze(YOUTUBE_URL, extractor=FakeExtractor(_single_video_target()))
        request = DownloadRequest(
            quality_label="1080p",
            destination=Path("/tmp/whatever"),
            filename_mode="original",
            filename_pattern=None,
        )
        run_plan = plan(request, analysis)
        self.assertEqual(run_plan.quality, QualityChoice(label="1080p"))
        self.assertTrue(run_plan.prefer_mp4)  # avc1/mp4a present
        self.assertEqual(run_plan.video_urls, [YOUTUBE_URL])

    def test_unavailable_quality_raises_with_real_menu(self):
        analysis = analyze(YOUTUBE_URL, extractor=FakeExtractor(_single_video_target()))
        request = DownloadRequest(
            quality_label="720p",  # not in SAMPLE_FORMATS (only 1080p/360p)
            destination=Path("/tmp/whatever"),
            filename_mode="original",
            filename_pattern=None,
        )
        with self.assertRaises(QualityUnavailableError) as ctx:
            plan(request, analysis)
        self.assertEqual([o.key for o in ctx.exception.menu], ["best", "1080p", "360p"])

    def test_webm_only_site_disables_prefer_mp4(self):
        target = _single_video_target(formats=WEBM_ONLY_FORMATS)
        analysis = analyze(YOUTUBE_URL, extractor=FakeExtractor(target))
        request = DownloadRequest(
            quality_label="best",
            destination=Path("/tmp/whatever"),
            filename_mode="original",
            filename_pattern=None,
        )
        run_plan = plan(request, analysis)
        self.assertFalse(run_plan.prefer_mp4)

    def test_playlist_quality_not_validated_upfront(self):
        # Playlists' per-item formats aren't known until download time,
        # so plan() must not reject a quality just because it isn't on
        # the fixed ladder-derived menu.
        target = _playlist_target([{"webpage_url": "https://example.com/1"}])
        analysis = analyze(PLAYLIST_URL, extractor=FakeExtractor(target))
        request = DownloadRequest(
            quality_label="1080p",
            destination=Path("/tmp/whatever"),
            filename_mode="original",
            filename_pattern=None,
        )
        run_plan = plan(request, analysis)  # must not raise
        self.assertTrue(run_plan.is_playlist)


class TestExecute(unittest.TestCase):
    def test_runs_through_injected_downloader_factory(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            target = _single_video_target()
            analysis = analyze(YOUTUBE_URL, extractor=FakeExtractor(target))
            request = DownloadRequest(
                quality_label="best",
                destination=destination,
                filename_mode="original",
                filename_pattern=None,
            )
            run_plan = plan(request, analysis)

            events = []
            result = execute(
                run_plan,
                progress_callback=events.append,
                downloader_factory=FakeDownloader,
            )

            self.assertEqual(result.downloaded, 1)
            self.assertEqual(result.failed, 0)
            self.assertTrue((destination / "Test Video.mp4").exists())
            statuses = [e.status for e in events]
            self.assertEqual(statuses, ["downloading", "finished"])


if __name__ == "__main__":
    unittest.main()
