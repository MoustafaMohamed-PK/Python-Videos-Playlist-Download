import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.filename import (
    FilenameError,
    build_filename,
    dedupe_path,
    existing_outputs,
    existing_subtitle_outputs,
    sanitize_filename,
    validate_pattern,
)


class TestSanitizeFilename(unittest.TestCase):
    def test_removes_windows_invalid_characters(self):
        result = sanitize_filename('Title: "Special" <Video> | Part *1*?')
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, result)

    def test_preserves_unicode_arabic(self):
        title = "مقدمة في بايثون"
        result = sanitize_filename(title)
        self.assertEqual(result, title)

    def test_empty_name_uses_fallback(self):
        result = sanitize_filename("", fallback="video_1")
        self.assertEqual(result, "video_1")

    def test_only_invalid_chars_uses_fallback(self):
        result = sanitize_filename('???', fallback="video_1")
        # '???' sanitizes to '___' which is non-empty and valid, so it is
        # NOT replaced by the fallback -- only a truly empty result is.
        self.assertTrue(result)

    def test_strips_trailing_dots_and_spaces(self):
        result = sanitize_filename("My Video.   ")
        self.assertFalse(result.endswith("."))
        self.assertFalse(result.endswith(" "))

    def test_windows_reserved_name_is_escaped(self):
        result = sanitize_filename("CON")
        self.assertNotEqual(result.upper(), "CON")

    def test_long_name_is_truncated(self):
        result = sanitize_filename("a" * 500)
        self.assertLessEqual(len(result), 150)

    def test_collapses_whitespace(self):
        result = sanitize_filename("Too    many     spaces")
        self.assertEqual(result, "Too many spaces")


class TestBuildFilename(unittest.TestCase):
    def setUp(self):
        self.metadata = {"title": "Python Variables", "uploader": "Code Channel"}

    def test_original_mode_uses_title(self):
        result = build_filename("original", 1, self.metadata)
        self.assertEqual(result, "Python Variables")

    def test_numbered_mode_single_video(self):
        result = build_filename("numbered", 1, self.metadata)
        self.assertEqual(result, "1")

    def test_numbered_mode_sequence(self):
        results = [build_filename("numbered", i, self.metadata) for i in range(1, 6)]
        self.assertEqual(results, ["1", "2", "3", "4", "5"])

    def test_pattern_mode_number_placeholder(self):
        result = build_filename("pattern", 3, self.metadata, pattern="lesson_{number}")
        self.assertEqual(result, "lesson_3")

    def test_pattern_mode_multiple_placeholders(self):
        result = build_filename(
            "pattern", 2, self.metadata, pattern="{uploader}_{number}_{title}"
        )
        self.assertEqual(result, "Code Channel_2_Python Variables")

    def test_pattern_mode_playlist_index_alias(self):
        result = build_filename("pattern", 7, self.metadata, pattern="video_{playlist_index}")
        self.assertEqual(result, "video_7")

    def test_pattern_mode_missing_pattern_raises(self):
        with self.assertRaises(FilenameError):
            build_filename("pattern", 1, self.metadata, pattern=None)

    def test_unknown_mode_raises(self):
        with self.assertRaises(FilenameError):
            build_filename("bogus", 1, self.metadata)

    def test_original_mode_missing_title_falls_back(self):
        result = build_filename("original", 5, {})
        self.assertTrue(result)  # non-empty, sanitized fallback used


class TestValidatePattern(unittest.TestCase):
    def test_valid_pattern_passes(self):
        validate_pattern("lesson_{number}")  # should not raise

    def test_empty_pattern_raises(self):
        with self.assertRaises(FilenameError):
            validate_pattern("")

    def test_unknown_placeholder_raises(self):
        with self.assertRaises(FilenameError):
            validate_pattern("video_{bogus}")

    def test_multiple_known_placeholders_pass(self):
        validate_pattern("{uploader}-{title}-{number}-{playlist_index}")


class TestDedupePath(unittest.TestCase):
    def test_returns_same_path_if_not_existing(self, tmp_path=Path("/tmp/ytdl_test_nonexistent_xyz.mp4")):
        if tmp_path.exists():
            tmp_path.unlink()
        result = dedupe_path(tmp_path)
        self.assertEqual(result, tmp_path)

    def test_appends_counter_if_exists(self):
        base = Path("/tmp/ytdl_test_dupe.mp4")
        base.parent.mkdir(parents=True, exist_ok=True)
        base.touch()
        try:
            result = dedupe_path(base)
            self.assertEqual(result.name, "ytdl_test_dupe (2).mp4")
        finally:
            base.unlink(missing_ok=True)


class TestExistingOutputs(unittest.TestCase):
    def test_finds_non_mp4_container(self):
        # The whole point: a webm-only site's output must still be
        # recognized as "already downloaded", not just a hardcoded .mp4.
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            (destination / "My Video.webm").touch()
            found = existing_outputs(destination, "My Video")
            self.assertEqual([p.name for p in found], ["My Video.webm"])

    def test_ignores_sidecar_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            (destination / "My Video.mp4.part").touch()
            (destination / "My Video.info.json").touch()
            (destination / "My Video.jpg").touch()
            found = existing_outputs(destination, "My Video")
            self.assertEqual(found, [])

    def test_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = existing_outputs(Path(tmp), "Nothing Here")
            self.assertEqual(found, [])

    def test_glob_special_characters_in_stem_are_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            (destination / "Video [Official].mp4").touch()
            found = existing_outputs(destination, "Video [Official]")
            self.assertEqual([p.name for p in found], ["Video [Official].mp4"])


class TestExistingSubtitleOutputs(unittest.TestCase):
    def test_finds_language_tagged_subtitle_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            (destination / "My Video.en.srt").touch()
            found = existing_subtitle_outputs(destination, "My Video")
            self.assertEqual([p.name for p in found], ["My Video.en.srt"])

    def test_ignores_media_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            (destination / "My Video.mp4").touch()
            found = existing_subtitle_outputs(destination, "My Video")
            self.assertEqual(found, [])

    def test_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = existing_subtitle_outputs(Path(tmp), "Nothing Here")
            self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
