import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.formats import (
    QualityChoice,
    available_heights,
    build_format_selector,
    describe_available_qualities,
    has_audio_only,
    quality_is_available,
)


SAMPLE_FORMATS = [
    {"format_id": "137", "height": 1080, "vcodec": "avc1", "acodec": "none"},
    {"format_id": "136", "height": 720, "vcodec": "avc1", "acodec": "none"},
    {"format_id": "18", "height": 360, "vcodec": "avc1", "acodec": "mp4a"},
    {"format_id": "140", "height": None, "vcodec": "none", "acodec": "mp4a"},
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


if __name__ == "__main__":
    unittest.main()
