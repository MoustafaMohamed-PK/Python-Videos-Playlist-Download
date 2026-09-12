import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.validators import (
    ValidationError,
    ensure_writable_directory,
    is_youtube_url,
    looks_like_playlist,
    validate_destination_path,
    validate_youtube_url,
)


class TestIsYoutubeUrl(unittest.TestCase):
    def test_standard_watch_url(self):
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_short_url(self):
        self.assertTrue(is_youtube_url("https://youtu.be/dQw4w9WgXcQ"))

    def test_bare_domain_without_scheme_rejected(self):
        self.assertFalse(is_youtube_url("youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_non_youtube_domain_rejected(self):
        self.assertFalse(is_youtube_url("https://vimeo.com/12345"))

    def test_empty_string_rejected(self):
        self.assertFalse(is_youtube_url(""))

    def test_none_rejected(self):
        self.assertFalse(is_youtube_url(None))  # type: ignore[arg-type]

    def test_playlist_url(self):
        self.assertTrue(
            is_youtube_url("https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx")
        )

    def test_mobile_subdomain(self):
        self.assertTrue(is_youtube_url("https://m.youtube.com/watch?v=abc123"))

    def test_lookalike_domain_rejected(self):
        self.assertFalse(is_youtube_url("https://youtube.com.evil.com/watch?v=abc"))


class TestLooksLikePlaylist(unittest.TestCase):
    def test_detects_list_param(self):
        self.assertTrue(
            looks_like_playlist("https://www.youtube.com/playlist?list=PLxxxx")
        )

    def test_watch_url_without_list_param(self):
        self.assertFalse(looks_like_playlist("https://www.youtube.com/watch?v=abc123"))

    def test_watch_url_with_list_param(self):
        self.assertTrue(
            looks_like_playlist("https://www.youtube.com/watch?v=abc123&list=PLxxxx")
        )


class TestValidateYoutubeUrl(unittest.TestCase):
    def test_valid_url_returns_stripped(self):
        result = validate_youtube_url("  https://youtu.be/abc123  ")
        self.assertEqual(result, "https://youtu.be/abc123")

    def test_empty_raises(self):
        with self.assertRaises(ValidationError):
            validate_youtube_url("")

    def test_invalid_url_raises(self):
        with self.assertRaises(ValidationError):
            validate_youtube_url("not a url at all")

    def test_non_youtube_url_raises(self):
        with self.assertRaises(ValidationError):
            validate_youtube_url("https://example.com/video")


class TestValidateDestinationPath(unittest.TestCase):
    def test_empty_raises(self):
        with self.assertRaises(ValidationError):
            validate_destination_path("")

    def test_strips_surrounding_quotes(self):
        result = validate_destination_path('"/tmp/some folder"')
        self.assertEqual(str(result), "/tmp/some folder")

    def test_handles_spaces_in_path(self):
        result = validate_destination_path("/tmp/My Videos")
        self.assertEqual(str(result), "/tmp/My Videos")

    def test_relative_path_preserved(self):
        result = validate_destination_path("./downloads")
        self.assertEqual(result, Path("./downloads"))

    def test_expands_user_home(self):
        result = validate_destination_path("~/Videos")
        self.assertFalse(str(result).startswith("~"))


class TestEnsureWritableDirectory(unittest.TestCase):
    def test_missing_directory_reports_does_not_exist(self):
        missing = Path(tempfile.gettempdir()) / "ytdl_definitely_missing_dir_xyz"
        if missing.exists():
            missing.rmdir()
        ok, err = ensure_writable_directory(missing)
        self.assertFalse(ok)
        self.assertEqual(err, "does_not_exist")

    def test_existing_writable_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, err = ensure_writable_directory(Path(tmp))
            self.assertTrue(ok)
            self.assertIsNone(err)

    def test_file_instead_of_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "not_a_dir.txt"
            file_path.write_text("hello")
            ok, err = ensure_writable_directory(file_path)
            self.assertFalse(ok)
            self.assertIn("not a directory", err)


if __name__ == "__main__":
    unittest.main()
