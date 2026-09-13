import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.subtitles import available_subtitle_options


class TestAvailableSubtitleOptions(unittest.TestCase):
    def test_manual_subtitles_labeled_without_qualification(self):
        info = {"subtitles": {"en": [{"name": "English", "ext": "vtt"}]}, "automatic_captions": {}}
        options = available_subtitle_options(info)
        self.assertEqual([(o.lang, o.label, o.auto_only) for o in options], [("en", "English", False)])

    def test_auto_only_language_is_marked(self):
        info = {"subtitles": {}, "automatic_captions": {"en": [{"name": "English", "ext": "vtt"}]}}
        options = available_subtitle_options(info)
        self.assertEqual(options[0].label, "English (auto-generated)")
        self.assertTrue(options[0].auto_only)

    def test_manual_track_preferred_when_language_has_both(self):
        info = {
            "subtitles": {"en": [{"name": "English", "ext": "vtt"}]},
            "automatic_captions": {"en": [{"name": "English", "ext": "vtt"}]},
        }
        options = available_subtitle_options(info)
        self.assertEqual(len(options), 1)
        self.assertFalse(options[0].auto_only)

    def test_manual_languages_sort_before_auto_only_ones(self):
        info = {
            "subtitles": {"es": [{"name": "Spanish"}]},
            "automatic_captions": {"ar": [{"name": "Arabic"}]},
        }
        options = available_subtitle_options(info)
        self.assertEqual([o.lang for o in options], ["es", "ar"])

    def test_missing_name_falls_back_to_lang_code(self):
        info = {"subtitles": {"de": [{"ext": "vtt"}]}, "automatic_captions": {}}
        options = available_subtitle_options(info)
        self.assertEqual(options[0].label, "de")

    def test_no_subtitle_data_returns_empty(self):
        self.assertEqual(available_subtitle_options({}), [])


if __name__ == "__main__":
    unittest.main()
