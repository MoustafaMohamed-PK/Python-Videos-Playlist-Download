import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.formats import (
    QualityChoice,
    QualityOption,
    available_heights,
    build_format_selector,
    build_quality_menu,
    describe_available_qualities,
    formats_support_mp4,
    has_audio_only,
    quality_is_available,
)


SAMPLE_FORMATS = [
    {"format_id": "137", "height": 1080, "vcodec": "avc1", "acodec": "none"},
    {"format_id": "136", "height": 720, "vcodec": "avc1", "acodec": "none"},
    {"format_id": "18", "height": 360, "vcodec": "avc1", "acodec": "mp4a"},
    {"format_id": "140", "height": None, "vcodec": "none", "acodec": "mp4a"},
]

# A webm/vp9/opus-only site (no avc1/mp4a anywhere) -- what a real
# non-YouTube site's catalogue can look like.
WEBM_ONLY_FORMATS = [
    {"format_id": "0", "height": 540, "vcodec": "vp9", "acodec": "none"},
    {"format_id": "1", "height": 360, "vcodec": "vp9", "acodec": "none"},
    {"format_id": "2", "height": None, "vcodec": "none", "acodec": "opus"},
]

# A single muxed format with no height metadata at all (some small
# sites only ever expose one take-it-or-leave-it format).
NO_HEIGHT_FORMATS = [
    {"format_id": "0", "height": None, "vcodec": "h264", "acodec": "aac"},
]

# A pure audio site (SoundCloud-shaped): every format is audio-only.
AUDIO_ONLY_FORMATS = [
    {"format_id": "0", "height": None, "vcodec": "none", "acodec": "opus"},
    {"format_id": "1", "height": None, "vcodec": "none", "acodec": "mp3"},
]


class TestBuildFormatSelector(unittest.TestCase):
    def test_audio_only_selector(self):
        selector = build_format_selector(QualityChoice(label="audio"))
        self.assertEqual(selector, "bestaudio/best")

    def test_best_selector(self):
        selector = build_format_selector(QualityChoice(label="best"))
        self.assertIn("bestvideo", selector)
        self.assertIn("bestaudio", selector)

    def test_specific_height_selector_includes_height(self):
        selector = build_format_selector(QualityChoice(label="1080p"))
        self.assertIn("1080", selector)

    def test_different_heights_produce_different_selectors(self):
        s720 = build_format_selector(QualityChoice(label="720p"))
        s480 = build_format_selector(QualityChoice(label="480p"))
        self.assertNotEqual(s720, s480)

    def test_odd_height_outside_fixed_ladder_works(self):
        # 540p isn't on QUALITY_LADDER (YouTube doesn't offer it), but
        # plenty of other sites (Vimeo) do -- the selector must still
        # build correctly for it.
        selector = build_format_selector(QualityChoice(label="540p"))
        self.assertIn("540", selector)

    def test_compatible_progressive_preferred_over_any_codec_merge(self):
        # Facebook reels can offer only AV1 video-only DASH streams plus
        # an H.264 progressive "hd" stream with unknown codec; the
        # progressive tier must come before the any-codec merge or the
        # AV1 merge wins and plays as a black screen.
        for label in ("best", "720p"):
            selector = build_format_selector(QualityChoice(label=label))
            tiers = selector.split("/")
            progressive = next(i for i, t in enumerate(tiers) if "vcodec!~=?" in t)
            any_merge = next(
                i for i, t in enumerate(tiers)
                if t.startswith("bestvideo*") and "vcodec" not in t
            )
            self.assertLess(progressive, any_merge, label)

    def test_tiktok_codec_names_and_hevc_handled(self):
        # TikTok reports "h264"/"aac" (not "avc1"/"mp4a") and serves its
        # top quality as HEVC ("bytevc1"), which many players can't show.
        selector = build_format_selector(QualityChoice(label="best"))
        self.assertIn("h264", selector)
        self.assertIn("aac", selector)
        self.assertIn("bytevc", selector)
        self.assertIn("hev", selector)


class TestQualityChoiceHeight(unittest.TestCase):
    def test_parses_height_from_any_label(self):
        self.assertEqual(QualityChoice(label="540p").height, 540)
        self.assertEqual(QualityChoice(label="240p").height, 240)
        self.assertEqual(QualityChoice(label="1080p").height, 1080)

    def test_non_height_labels_have_no_height(self):
        self.assertIsNone(QualityChoice(label="best").height)
        self.assertIsNone(QualityChoice(label="audio").height)


class TestAvailableHeights(unittest.TestCase):
    def test_extracts_distinct_heights_sorted_desc(self):
        heights = available_heights(SAMPLE_FORMATS)
        self.assertEqual(heights, [1080, 720, 360])

    def test_empty_formats_list(self):
        self.assertEqual(available_heights([]), [])

    def test_ignores_audio_only_formats(self):
        heights = available_heights(SAMPLE_FORMATS)
        self.assertNotIn(None, heights)


class TestHasAudioOnly(unittest.TestCase):
    def test_detects_audio_only_format(self):
        self.assertTrue(has_audio_only(SAMPLE_FORMATS))

    def test_no_audio_only_in_video_formats(self):
        video_only = [f for f in SAMPLE_FORMATS if f.get("vcodec") != "none"]
        self.assertFalse(has_audio_only(video_only))


class TestQualityIsAvailable(unittest.TestCase):
    def test_best_always_available_with_formats(self):
        self.assertTrue(quality_is_available(QualityChoice(label="best"), SAMPLE_FORMATS))

    def test_best_not_available_with_no_formats(self):
        self.assertFalse(quality_is_available(QualityChoice(label="best"), []))

    def test_exact_height_available(self):
        self.assertTrue(quality_is_available(QualityChoice(label="1080p"), SAMPLE_FORMATS))

    def test_exact_height_not_available(self):
        self.assertFalse(quality_is_available(QualityChoice(label="2160p"), SAMPLE_FORMATS))

    def test_audio_only_available(self):
        self.assertTrue(quality_is_available(QualityChoice(label="audio"), SAMPLE_FORMATS))


class TestDescribeAvailableQualities(unittest.TestCase):
    def test_lists_available_in_descending_order(self):
        labels = describe_available_qualities(SAMPLE_FORMATS)
        self.assertEqual(labels[:3], ["1080p", "720p", "360p"])

    def test_includes_audio_when_present(self):
        labels = describe_available_qualities(SAMPLE_FORMATS)
        self.assertIn("audio", labels)

    def test_empty_when_no_formats(self):
        self.assertEqual(describe_available_qualities([]), [])


class TestBuildQualityMenu(unittest.TestCase):
    def test_no_formats_offers_best_only(self):
        menu = build_quality_menu([])
        self.assertEqual([o.key for o in menu], ["best"])

    def test_includes_odd_height_and_audio(self):
        menu = build_quality_menu(WEBM_ONLY_FORMATS)
        keys = [o.key for o in menu]
        self.assertEqual(keys, ["best", "540p", "360p", "audio"])

    def test_single_muxed_format_with_no_height_offers_best_only(self):
        menu = build_quality_menu(NO_HEIGHT_FORMATS)
        self.assertEqual([o.key for o in menu], ["best"])

    def test_audio_only_site_offers_audio_only(self):
        menu = build_quality_menu(AUDIO_ONLY_FORMATS)
        self.assertEqual([o.key for o in menu], ["audio"])

    def test_matches_sample_formats_ladder_heights(self):
        menu = build_quality_menu(SAMPLE_FORMATS)
        self.assertEqual([o.key for o in menu], ["best", "1080p", "720p", "360p", "audio"])


class TestQualityIsAvailableLenient(unittest.TestCase):
    def test_audio_available_on_webm_only_site(self):
        self.assertTrue(quality_is_available(QualityChoice(label="audio"), WEBM_ONLY_FORMATS))

    def test_audio_available_when_no_heights_reported_at_all(self):
        # Degenerate case: a format with no height and no explicit
        # vcodec == "none" marker still counts as "audio available"
        # since there's nothing else it could resolve to.
        self.assertTrue(quality_is_available(QualityChoice(label="audio"), NO_HEIGHT_FORMATS))

    def test_odd_height_is_available(self):
        self.assertTrue(quality_is_available(QualityChoice(label="540p"), WEBM_ONLY_FORMATS))


class TestFormatsSupportMp4(unittest.TestCase):
    def test_true_when_avc1_present(self):
        self.assertTrue(formats_support_mp4(SAMPLE_FORMATS))

    def test_false_for_webm_vp9_opus_only_site(self):
        self.assertFalse(formats_support_mp4(WEBM_ONLY_FORMATS))

    def test_true_for_h264_aac(self):
        self.assertTrue(formats_support_mp4(NO_HEIGHT_FORMATS))

    def test_false_for_empty_formats(self):
        self.assertFalse(formats_support_mp4([]))


if __name__ == "__main__":
    unittest.main()
