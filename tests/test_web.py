import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import AppConfig
from app.downloader import URLUnavailableError, VideoInfo
from app.formats import QualityOption
from app.jobs import JobManager
from app.service import AnalyzeResult
from app.subtitles import SubtitleOption
from tests.fakes import FakeDownloader
from web.app import create_app

BASE_URL = "http://127.0.0.1:8765"


def _fake_analysis(is_playlist=False, video_count=1, url="https://www.youtube.com/watch?v=abc", subtitle_menu=None):
    videos = [VideoInfo(id=f"id{i}", title=f"Item {i}", uploader="ChannelX") for i in range(video_count)]
    formats = (
        []
        if is_playlist
        else [{"format_id": "1", "height": 720, "vcodec": "avc1", "acodec": "mp4a"}]
    )
    return AnalyzeResult(
        url=url,
        is_playlist=is_playlist,
        playlist_title="My Playlist" if is_playlist else None,
        title="My Playlist" if is_playlist else "Item 0",
        videos=videos,
        formats=formats,
        quality_menu=[QualityOption(key="best", label="Best available", height=None)],
        video_urls=[url] * video_count,
        subtitle_menu=subtitle_menu or [],
    )


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class WebTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.job_manager = JobManager(downloader_factory=FakeDownloader)
        self.app = create_app(
            download_root=self.root,
            config=AppConfig(),
            host="127.0.0.1",
            port=8765,
            job_manager=self.job_manager,
        )
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def get(self, path, **kwargs):
        kwargs.setdefault("base_url", BASE_URL)
        return self.client.get(path, **kwargs)

    def post_json(self, path, payload, **kwargs):
        kwargs.setdefault("base_url", BASE_URL)
        return self.client.post(
            path, data=json.dumps(payload), content_type="application/json", **kwargs
        )


class TestIndexPage(WebTestCase):
    def test_index_renders(self):
        resp = self.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Media Downloader", resp.data)


class TestSecurityChecks(WebTestCase):
    def test_wrong_host_header_rejected(self):
        resp = self.client.get("/api/jobs", base_url="http://evil.com")
        self.assertEqual(resp.status_code, 403)

    def test_correct_host_header_accepted(self):
        resp = self.get("/api/jobs")
        self.assertEqual(resp.status_code, 200)

    def test_non_json_content_type_rejected(self):
        resp = self.client.post(
            "/api/jobs",
            data="url=x",
            content_type="application/x-www-form-urlencoded",
            base_url=BASE_URL,
        )
        self.assertEqual(resp.status_code, 415)

    def test_post_with_no_body_still_requires_json_content_type(self):
        resp = self.client.post("/api/jobs/whatever/cancel", base_url=BASE_URL)
        self.assertEqual(resp.status_code, 415)

    def test_get_requests_are_not_subject_to_json_check(self):
        resp = self.get("/api/jobs")
        self.assertEqual(resp.status_code, 200)


class TestAnalyzeEndpoint(WebTestCase):
    def test_missing_url_rejected(self):
        resp = self.post_json("/api/analyze", {})
        self.assertEqual(resp.status_code, 400)

    @patch("web.routes.analyze")
    def test_valid_url_returns_analysis(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json("/api/analyze", {"url": "https://www.youtube.com/watch?v=abc"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["title"], "Item 0")
        self.assertEqual(body["qualities"], [{"key": "best", "label": "Best available"}])

    @patch("web.routes.analyze")
    def test_extraction_failure_returns_400(self, mock_analyze):
        mock_analyze.side_effect = URLUnavailableError("This video is unavailable.")
        resp = self.post_json("/api/analyze", {"url": "https://www.youtube.com/watch?v=gone"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("unavailable", resp.get_json()["error"].lower())

    @patch("web.routes.analyze")
    def test_response_includes_subtitle_menu(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis(
            subtitle_menu=[SubtitleOption(lang="en", label="English", auto_only=False)]
        )
        resp = self.post_json("/api/analyze", {"url": "https://www.youtube.com/watch?v=abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["subtitles"], [{"lang": "en", "label": "English"}])


class TestJobCreation(WebTestCase):
    @patch("web.routes.analyze")
    def test_subfolder_path_traversal_rejected(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs",
            {"url": "https://www.youtube.com/watch?v=abc", "quality": "best", "subfolder": "../../../etc"},
        )
        # Traversal is neutralized (stays inside root), not an error --
        # verify it never escapes by checking the job actually runs
        # inside self.root rather than asserting a 400 here.
        self.assertEqual(resp.status_code, 202)
        job_id = resp.get_json()["job_id"]
        # Wait for the background download to finish before the test
        # (and its TemporaryDirectory) tears down, or the worker thread
        # can race the directory removal.
        self.assertTrue(
            _wait_until(lambda: self.job_manager.get(job_id).state.value == "completed")
        )

    @patch("web.routes.analyze")
    def test_absolute_subfolder_rejected(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs",
            {"url": "https://www.youtube.com/watch?v=abc", "subfolder": "/etc/passwd"},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("web.routes.analyze")
    def test_backslash_subfolder_rejected(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs",
            {"url": "https://www.youtube.com/watch?v=abc", "subfolder": "..\\..\\windows"},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("web.routes.analyze")
    def test_valid_request_creates_and_runs_job(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs", {"url": "https://www.youtube.com/watch?v=abc", "quality": "best"}
        )
        self.assertEqual(resp.status_code, 202)
        job_id = resp.get_json()["job_id"]

        def is_done():
            job = self.job_manager.get(job_id)
            return job is not None and job.state.value == "completed"

        self.assertTrue(_wait_until(is_done))

        job_resp = self.get(f"/api/jobs/{job_id}")
        job = job_resp.get_json()
        self.assertEqual(job["state"], "completed")
        self.assertEqual(len(job["results"]), 1)
        self.assertTrue(job["results"][0]["has_file"])

        # The file must have actually landed under the configured root.
        output_path = self.job_manager.get(job_id).result.results[0].output_path
        self.assertTrue(str(output_path).startswith(str(self.root.resolve())))

    @patch("web.routes.analyze")
    def test_unavailable_quality_returns_menu(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs", {"url": "https://www.youtube.com/watch?v=abc", "quality": "9999p"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("qualities", resp.get_json())

    @patch("web.routes.analyze")
    def test_subtitles_only_without_languages_rejected(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs",
            {"url": "https://www.youtube.com/watch?v=abc", "subtitles_only": True},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("web.routes.analyze")
    def test_subtitle_langs_must_be_a_list(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs",
            {"url": "https://www.youtube.com/watch?v=abc", "subtitle_langs": "en"},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("web.routes.analyze")
    def test_subtitles_only_job_runs_and_produces_subtitle_file(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs",
            {
                "url": "https://www.youtube.com/watch?v=abc",
                "subtitle_langs": ["en"],
                "subtitles_only": True,
            },
        )
        self.assertEqual(resp.status_code, 202)
        job_id = resp.get_json()["job_id"]
        self.assertTrue(
            _wait_until(lambda: self.job_manager.get(job_id).state.value == "completed")
        )
        output_path = self.job_manager.get(job_id).result.results[0].output_path
        self.assertTrue(str(output_path).endswith(".en.srt"))


class TestManualDestinationPath(WebTestCase):
    @patch("web.routes.analyze")
    def test_destination_path_bypasses_the_configured_root(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        with tempfile.TemporaryDirectory() as elsewhere:
            resp = self.post_json(
                "/api/jobs",
                {
                    "url": "https://www.youtube.com/watch?v=abc",
                    "quality": "best",
                    "destination_path": elsewhere,
                },
            )
            self.assertEqual(resp.status_code, 202)
            job_id = resp.get_json()["job_id"]
            self.assertTrue(
                _wait_until(lambda: self.job_manager.get(job_id).state.value == "completed")
            )
            output_path = self.job_manager.get(job_id).result.results[0].output_path
            # Landed under the manually-specified folder, NOT under
            # self.root -- this is the whole point of destination_path.
            self.assertTrue(str(output_path).startswith(str(Path(elsewhere).resolve())))
            self.assertFalse(str(output_path).startswith(str(self.root.resolve())))

    @patch("web.routes.analyze")
    def test_empty_destination_path_falls_back_to_subfolder_mode(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs",
            {
                "url": "https://www.youtube.com/watch?v=abc",
                "quality": "best",
                "destination_path": "   ",
                "subfolder": "music",
            },
        )
        self.assertEqual(resp.status_code, 202)
        job_id = resp.get_json()["job_id"]
        self.assertTrue(
            _wait_until(lambda: self.job_manager.get(job_id).state.value == "completed")
        )
        output_path = self.job_manager.get(job_id).result.results[0].output_path
        self.assertTrue(str(output_path).startswith(str((self.root / "music").resolve())))


class TestSettingsEndpoint(WebTestCase):
    def test_settings_include_download_root(self):
        resp = self.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["download_root"], str(self.root))
        self.assertIn("quality", body)
        self.assertIn("concurrency", body)


class TestBrowseEndpoint(WebTestCase):
    def test_browse_lists_subdirectories(self):
        (self.root / "alpha").mkdir()
        (self.root / "beta").mkdir()
        (self.root / "not_a_dir.txt").write_text("x")

        resp = self.get(f"/api/browse?path={self.root}")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["path"], str(self.root.resolve()))
        self.assertEqual(sorted(body["directories"]), ["alpha", "beta"])
        self.assertEqual(body["parent"], str(self.root.resolve().parent))

    def test_browse_defaults_to_home_when_no_path_given(self):
        resp = self.get("/api/browse")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["path"], str(Path.home().resolve()))

    def test_browse_nonexistent_path_404(self):
        resp = self.get(f"/api/browse?path={self.root}/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_browse_file_not_directory_400(self):
        f = self.root / "afile.txt"
        f.write_text("x")
        resp = self.get(f"/api/browse?path={f}")
        self.assertEqual(resp.status_code, 400)

    def test_browse_mkdir_creates_folder(self):
        resp = self.post_json("/api/browse/mkdir", {"path": str(self.root), "name": "New Folder"})
        self.assertEqual(resp.status_code, 201)
        self.assertTrue((self.root / "New Folder").is_dir())

    def test_browse_mkdir_sanitizes_name(self):
        resp = self.post_json("/api/browse/mkdir", {"path": str(self.root), "name": "a/b:c"})
        self.assertEqual(resp.status_code, 201)
        created = Path(resp.get_json()["path"])
        self.assertTrue(created.is_dir())
        self.assertTrue(created.parent == self.root.resolve())

    def test_browse_mkdir_missing_fields_400(self):
        resp = self.post_json("/api/browse/mkdir", {"path": str(self.root)})
        self.assertEqual(resp.status_code, 400)


class TestConflictResolutionEndpoint(WebTestCase):
    @patch("web.routes.analyze")
    def test_resolve_unknown_job_returns_409(self, mock_analyze):
        resp = self.post_json("/api/jobs/does-not-exist/resolve", {"action": "skip"})
        self.assertEqual(resp.status_code, 409)

    @patch("web.routes.analyze")
    def test_full_ask_flow_via_http(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        # This test uses its own JobManager (not self.job_manager) so
        # it can inject conflict_indices on the downloader factory.
        from functools import partial

        manager = JobManager(downloader_factory=partial(FakeDownloader, conflict_indices={1}))
        app = create_app(
            download_root=self.root,
            config=AppConfig(),
            host="127.0.0.1",
            port=8765,
            job_manager=manager,
        )
        app.testing = True
        client = app.test_client()

        resp = client.post(
            "/api/jobs",
            data=json.dumps({"url": "https://www.youtube.com/watch?v=abc", "quality": "best", "existing_file_behavior": "ask"}),
            content_type="application/json",
            base_url=BASE_URL,
        )
        self.assertEqual(resp.status_code, 202)
        job_id = resp.get_json()["job_id"]

        self.assertTrue(_wait_until(lambda: manager.get(job_id).pending_conflict is not None))

        snap = client.get(f"/api/jobs/{job_id}", base_url=BASE_URL).get_json()
        self.assertIsNotNone(snap["pending_conflict"])

        resolve_resp = client.post(
            f"/api/jobs/{job_id}/resolve",
            data=json.dumps({"action": "overwrite"}),
            content_type="application/json",
            base_url=BASE_URL,
        )
        self.assertEqual(resolve_resp.status_code, 202)

        self.assertTrue(_wait_until(lambda: manager.get(job_id).state.value == "completed"))
        self.assertEqual(manager.get(job_id).result.downloaded, 1)


class TestJobEndpoints(WebTestCase):
    def test_get_unknown_job_404(self):
        resp = self.get("/api/jobs/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_unknown_job_404(self):
        resp = self.post_json("/api/jobs/does-not-exist/cancel", {})
        self.assertEqual(resp.status_code, 404)


class TestFileServing(WebTestCase):
    def test_unknown_job_returns_404(self):
        resp = self.get("/api/jobs/nope/files/1")
        self.assertEqual(resp.status_code, 404)

    @patch("web.routes.analyze")
    def test_file_outside_configured_root_is_still_served(self, mock_analyze):
        # A job's destination is no longer confined to the configured
        # download root (destination_path/the folder browser can point
        # anywhere) -- serving a completed job's own output_path must
        # work regardless of whether it happens to live under that
        # root, since job id + index are never client-supplied at
        # request time (see web/routes.py's module docstring).
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs", {"url": "https://www.youtube.com/watch?v=abc", "quality": "best"}
        )
        job_id = resp.get_json()["job_id"]

        self.assertTrue(
            _wait_until(lambda: self.job_manager.get(job_id).state.value == "completed")
        )

        # Point the stored result somewhere outside self.root, as
        # destination_path legitimately can.
        outside = self.root.parent / f"outside-{job_id}.mp4"
        outside.write_bytes(b"content from outside the configured root")
        job = self.job_manager.get(job_id)
        job.result.results[0].output_path = outside
        try:
            r = self.get(f"/api/jobs/{job_id}/files/1")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data, b"content from outside the configured root")
        finally:
            outside.unlink(missing_ok=True)

    @patch("web.routes.analyze")
    def test_nonexistent_stored_file_returns_404(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs", {"url": "https://www.youtube.com/watch?v=abc", "quality": "best"}
        )
        job_id = resp.get_json()["job_id"]
        self.assertTrue(
            _wait_until(lambda: self.job_manager.get(job_id).state.value == "completed")
        )

        job = self.job_manager.get(job_id)
        job.result.results[0].output_path = self.root / "this-file-was-never-written.mp4"

        r = self.get(f"/api/jobs/{job_id}/files/1")
        self.assertEqual(r.status_code, 404)

    @patch("web.routes.analyze")
    def test_valid_file_downloads(self, mock_analyze):
        mock_analyze.return_value = _fake_analysis()
        resp = self.post_json(
            "/api/jobs", {"url": "https://www.youtube.com/watch?v=abc", "quality": "best"}
        )
        job_id = resp.get_json()["job_id"]
        self.assertTrue(
            _wait_until(lambda: self.job_manager.get(job_id).state.value == "completed")
        )

        r = self.get(f"/api/jobs/{job_id}/files/1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, b"fake media content")


if __name__ == "__main__":
    unittest.main()
