import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sites import UnsupportedSiteError, match_extractor, validate_media_url
from app.validators import ValidationError

# NOTE: match_extractor() is pure regex matching against yt-dlp's bundled
# extractor list (SiteClass._VALID_URL patterns) -- no network access, so
# these tests run offline like the rest of the suite.


class TestMatchExtractor(unittest.TestCase):
    def test_youtube_watch_url(self):
        match = match_extractor("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(match.extractor, "Youtube")
        self.assertFalse(match.generic_only)

    def test_youtube_short_url(self):
        match = match_extractor("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(match.extractor, "Youtube")

    def test_vimeo_url(self):
        match = match_extractor("https://vimeo.com/12345")
        self.assertEqual(match.extractor, "Vimeo")
        self.assertFalse(match.generic_only)

    def test_lookalike_domain_falls_back_to_generic(self):
        # Anti-spoofing: a domain that merely contains "youtube.com" must
        # NOT be matched by the real Youtube extractor.
        match = match_extractor("https://youtube.com.evil.com/watch?v=abc")
        self.assertNotEqual(match.extractor, "Youtube")
        self.assertTrue(match.generic_only)

    def test_unrecognized_but_plausible_url_matches_generic(self):
        match = match_extractor("https://some-random-unknown-site.example/video/1")
        self.assertTrue(match.supported)
        self.assertTrue(match.generic_only)

    def test_result_is_stable_across_calls(self):
        first = match_extractor("https://vimeo.com/12345")
        second = match_extractor("https://vimeo.com/12345")
        self.assertEqual(first, second)


class TestValidateMediaUrl(unittest.TestCase):
    def test_valid_url_returns_stripped(self):
        result = validate_media_url("  https://youtu.be/abc123  ")
        self.assertEqual(result, "https://youtu.be/abc123")

    def test_empty_raises(self):
        with self.assertRaises(ValidationError):
            validate_media_url("")

    def test_bare_domain_without_scheme_rejected(self):
        with self.assertRaises(ValidationError):
            validate_media_url("youtube.com/watch?v=dQw4w9WgXcQ")

    def test_non_http_scheme_rejected(self):
        with self.assertRaises(ValidationError):
            validate_media_url("ftp://example.com/video.mp4")

    def test_javascript_scheme_rejected(self):
        with self.assertRaises(ValidationError):
            validate_media_url("javascript:alert(1)")

    def test_garbage_string_rejected(self):
        with self.assertRaises(ValidationError):
            validate_media_url("not a url at all")

    def test_non_youtube_site_accepted(self):
        # The whole point of this feature: a non-YouTube, non-lookalike
        # site must be accepted, not rejected the way the old
        # YouTube-only validator would have.
        result = validate_media_url("https://vimeo.com/12345")
        self.assertEqual(result, "https://vimeo.com/12345")

    def test_generic_only_rejected_when_disallowed(self):
        with self.assertRaises(UnsupportedSiteError):
            validate_media_url(
                "https://some-random-unknown-site.example/video/1",
                allow_generic=False,
            )

    def test_generic_only_accepted_by_default(self):
        result = validate_media_url("https://some-random-unknown-site.example/video/1")
        self.assertEqual(result, "https://some-random-unknown-site.example/video/1")


if __name__ == "__main__":
    unittest.main()
