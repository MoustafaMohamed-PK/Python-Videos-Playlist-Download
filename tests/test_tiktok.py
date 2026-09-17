import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sites import match_extractor
from app.tiktok import is_tiktok_url, normalize_tiktok_url

CANONICAL = "https://www.tiktok.com/@scout2015/video/6718335390845095173"


def _no_network(*_args):
    raise AssertionError("network access not expected")


def _redirects_to(target):
    calls = []

    def resolve(url):
        calls.append(url)
        return target

    resolve.calls = calls
    return resolve


def _oembed(username):
    return lambda _url: {"author_unique_id": username}


def _failing(_url):
    raise OSError("offline")


class TestNormalizeTikTokUrl(unittest.TestCase):
    def normalize(self, url, resolve=_no_network, oembed=_no_network):
        return normalize_tiktok_url(url, resolve_redirect=resolve, fetch_oembed=oembed)

    def test_non_tiktok_url_untouched(self):
        url = "https://www.facebook.com/share/r/19SB56Pszr/"
        self.assertEqual(self.normalize(url), url)

    def test_lookalike_domain_is_not_tiktok(self):
        self.assertFalse(is_tiktok_url("https://tiktok.com.evil.example/@a/video/1"))
        self.assertFalse(is_tiktok_url("https://nottiktok.com/@a/video/1"))

    def test_canonical_url_strips_share_query(self):
        self.assertEqual(self.normalize(CANONICAL + "?is_from_webapp=1&sender_device=pc"), CANONICAL)

    def test_lite_and_mobile_video_urls_move_to_www(self):
        for host in ("lite.tiktok.com", "m.tiktok.com", "tiktok.com"):
            url = f"https://{host}/@scout2015/video/6718335390845095173"
            self.assertEqual(self.normalize(url), CANONICAL, host)

    def test_lite_short_link_resolved(self):
        resolve = _redirects_to(CANONICAL + "?_r=1")
        result = self.normalize("https://lite.tiktok.com/t/ZP9BLDBh-Brx/", resolve=resolve)
        self.assertEqual(result, CANONICAL)
        self.assertEqual(resolve.calls, ["https://www.tiktok.com/t/ZP9BLDBh-Brx/"])

    def test_vt_short_link_resolved(self):
        resolve = _redirects_to(CANONICAL)
        self.assertEqual(self.normalize("https://vt.tiktok.com/ZSabc123/", resolve=resolve), CANONICAL)

    def test_short_link_resolving_to_id_only_url_gets_username(self):
        resolve = _redirects_to("https://www.tiktok.com/@/video/6718335390845095173?_r=1")
        result = self.normalize("https://vm.tiktok.com/ZMabc/", resolve=resolve, oembed=_oembed("scout2015"))
        self.assertEqual(result, CANONICAL)

    def test_short_link_resolution_failure_keeps_short_link(self):
        result = self.normalize("https://lite.tiktok.com/t/ZTabc/", resolve=_failing)
        self.assertEqual(result, "https://www.tiktok.com/t/ZTabc/")

    def test_id_only_shapes_get_username(self):
        for url in (
            "https://www.tiktok.com/video/6718335390845095173",
            "https://www.tiktok.com/@/video/6718335390845095173",
            "https://www.tiktok.com/embed/v2/6718335390845095173",
            "https://m.tiktok.com/v/6718335390845095173.html",
        ):
            self.assertEqual(self.normalize(url, oembed=_oembed("scout2015")), CANONICAL, url)

    def test_id_only_oembed_failure_falls_back(self):
        result = self.normalize("https://m.tiktok.com/v/6718335390845095173.html", oembed=_failing)
        self.assertEqual(result, "https://www.tiktok.com/@/video/6718335390845095173")

    def test_unsafe_oembed_username_ignored(self):
        result = self.normalize(
            "https://www.tiktok.com/video/6718335390845095173", oembed=_oembed("../evil")
        )
        self.assertEqual(result, "https://www.tiktok.com/@/video/6718335390845095173")

    def test_normalized_urls_match_tiktok_extractor(self):
        self.assertEqual(match_extractor(CANONICAL).extractor, "TikTok")
        self.assertEqual(
            match_extractor(self.normalize("https://lite.tiktok.com/t/ZTabc/", resolve=_failing)).extractor,
            "TikTokVM",
        )


class TestTikTokErrors(unittest.TestCase):
    def test_blocked_or_forbidden_post_reported_as_unavailable(self):
        from app.downloader import URLUnavailableError, classify_ytdlp_error

        for raw in (
            "ERROR: [TikTok] 7206: Your IP address is blocked from accessing this post",
            "ERROR: [TikTok] 6748: Unable to download webpage: HTTP Error 403: Forbidden",
        ):
            self.assertIsInstance(classify_ytdlp_error(Exception(raw)), URLUnavailableError, raw)

    def test_other_sites_403_still_network_error(self):
        from app.downloader import NetworkError, classify_ytdlp_error

        err = classify_ytdlp_error(Exception("ERROR: [vimeo] 1: Unable to download webpage: HTTP Error 403"))
        self.assertIsInstance(err, NetworkError)


class TestTikTokRetry(unittest.TestCase):
    def _fake_ydl(self, outcomes):
        import yt_dlp

        calls = []

        class FakeYDL:
            def __init__(self, _opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download=False):
                calls.append(url)
                outcome = outcomes.pop(0)
                if isinstance(outcome, str):
                    raise yt_dlp.utils.DownloadError(outcome)
                return outcome

        return FakeYDL, calls

    def test_transient_403_retried_then_succeeds(self):
        from unittest import mock

        from app import downloader

        forbidden = "ERROR: [TikTok] 1: Unable to download webpage: HTTP Error 403: Forbidden"
        fake, calls = self._fake_ydl([forbidden, forbidden, {"id": "1", "formats": [{"format_id": "a"}]}])
        with mock.patch.object(downloader.yt_dlp, "YoutubeDL", fake), mock.patch.object(downloader.time, "sleep"):
            formats = downloader.fetch_formats_for_video(CANONICAL)
        self.assertEqual(formats, [{"format_id": "a"}])
        self.assertEqual(len(calls), 3)

    def test_non_tiktok_403_not_retried(self):
        from unittest import mock

        from app import downloader

        fake, calls = self._fake_ydl(["ERROR: [vimeo] 1: Unable to download webpage: HTTP Error 403"])
        with mock.patch.object(downloader.yt_dlp, "YoutubeDL", fake), mock.patch.object(downloader.time, "sleep"):
            with self.assertRaises(downloader.DownloadAppError):
                downloader.fetch_formats_for_video("https://vimeo.com/1")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
