import sys
import tempfile
import time
import unittest
import unittest.mock
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.formats import QualityChoice
from app.jobs import JobManager, JobState
from app.service import RunPlan
from tests.fakes import FakeDownloader


def _plan(
    destination: Path,
    video_count: int = 2,
    title: str = "Test Job",
    existing_file_behavior: str = "skip",
) -> RunPlan:
    return RunPlan(
        quality=QualityChoice(label="best"),
        destination=destination,
        filename_mode="original",
        filename_pattern=None,
        existing_file_behavior=existing_file_behavior,
        prefer_mp4=True,
        video_urls=[f"https://example.com/{i}" for i in range(video_count)],
        metadatas=[{"title": f"item{i}", "uploader": "x"} for i in range(video_count)],
        title=title,
        is_playlist=video_count > 1,
        video_count=video_count,
        concurrency=1,
        concurrent_fragments=4,
    )


def _wait_until(predicate, timeout=2.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestJobLifecycle(unittest.TestCase):
    def test_submit_runs_job_to_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=FakeDownloader)
            job_id = manager.submit(_plan(Path(tmp)))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED))

            job = manager.get(job_id)
            self.assertEqual(job.result.downloaded, 2)
            self.assertEqual(job.result.failed, 0)

    def test_snapshot_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=FakeDownloader)
            job_id = manager.submit(_plan(Path(tmp), title="My Video"))
            _wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED)

            snap = manager.get(job_id).snapshot()
            self.assertEqual(snap["id"], job_id)
            self.assertEqual(snap["state"], "completed")
            self.assertEqual(snap["title"], "My Video")
            self.assertEqual(snap["progress"]["completed"], 2)
            self.assertEqual(len(snap["results"]), 2)

    def test_get_unknown_job_returns_none(self):
        manager = JobManager(downloader_factory=FakeDownloader)
        self.assertIsNone(manager.get("does-not-exist"))

    def test_list_returns_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=FakeDownloader)
            first = manager.submit(_plan(Path(tmp)))
            _wait_until(lambda: manager.get(first).state == JobState.COMPLETED)
            second = manager.submit(_plan(Path(tmp)))
            _wait_until(lambda: manager.get(second).state == JobState.COMPLETED)

            ids = [job.id for job in manager.list()]
            self.assertEqual(ids, [second, first])

    def test_history_trims_completed_jobs_beyond_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=FakeDownloader, history_limit=2)
            ids = []
            for _ in range(4):
                job_id = manager.submit(_plan(Path(tmp)))
                _wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED)
                ids.append(job_id)

            self.assertEqual(len(manager.list()), 2)
            # The two most recent survive; the earliest two are trimmed.
            self.assertIsNone(manager.get(ids[0]))
            self.assertIsNotNone(manager.get(ids[-1]))


class TestJobCancellation(unittest.TestCase):
    def test_cancel_stops_a_running_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            slow_factory = partial(FakeDownloader, delay=0.2)
            manager = JobManager(downloader_factory=slow_factory)
            job_id = manager.submit(_plan(Path(tmp), video_count=5))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.RUNNING))
            self.assertTrue(manager.cancel(job_id))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.CANCELLED, timeout=3))
            job = manager.get(job_id)
            self.assertLess(job.result.downloaded, 5)

    def test_cancel_unknown_job_returns_false(self):
        manager = JobManager(downloader_factory=FakeDownloader)
        self.assertFalse(manager.cancel("does-not-exist"))


class TestJobSubscribers(unittest.TestCase):
    def test_subscriber_receives_progress_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=partial(FakeDownloader, delay=0.02))
            queue = manager.subscribe()  # subscribe before submitting -- one global feed
            job_id = manager.submit(_plan(Path(tmp)))

            payload = queue.get(timeout=2)
            self.assertEqual(payload["id"], job_id)
            self.assertIn("state", payload)

    def test_subscriber_sees_updates_from_multiple_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=FakeDownloader)
            queue = manager.subscribe()
            first = manager.submit(_plan(Path(tmp)))
            second = manager.submit(_plan(Path(tmp)))
            _wait_until(lambda: manager.get(first).state == JobState.COMPLETED)
            _wait_until(lambda: manager.get(second).state == JobState.COMPLETED)

            seen_ids = set()
            while not queue.empty():
                seen_ids.add(queue.get_nowait()["id"])
            self.assertEqual(seen_ids, {first, second})

    def test_unsubscribe_stops_future_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=FakeDownloader)
            queue = manager.subscribe()
            job_id = manager.submit(_plan(Path(tmp)))
            _wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED)
            manager.unsubscribe(queue)

            # Draining what's already queued must not raise, and no
            # exception should occur publishing after unsubscribe.
            while not queue.empty():
                queue.get_nowait()
            manager._publish({"probe": True})  # must not raise


class TestAnalyzeCache(unittest.TestCase):
    def test_cache_hit_returns_analysis(self):
        manager = JobManager(downloader_factory=FakeDownloader)
        sentinel = object()
        manager.cache_analysis("https://example.com/v", sentinel)
        self.assertIs(manager.cached_analysis("https://example.com/v"), sentinel)

    def test_cache_miss_returns_none(self):
        manager = JobManager(downloader_factory=FakeDownloader)
        self.assertIsNone(manager.cached_analysis("https://example.com/never-cached"))

    def test_expired_entry_is_evicted(self):
        manager = JobManager(downloader_factory=FakeDownloader)
        sentinel = object()
        manager.cache_analysis("https://example.com/v", sentinel)
        # Simulate expiry without sleeping the real TTL.
        analysis, _ = manager._analyze_cache["https://example.com/v"]
        manager._analyze_cache["https://example.com/v"] = (analysis, time.time() - 1)

        self.assertIsNone(manager.cached_analysis("https://example.com/v"))
        self.assertNotIn("https://example.com/v", manager._analyze_cache)


class TestJobConflicts(unittest.TestCase):
    def test_pending_conflict_appears_in_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=partial(FakeDownloader, conflict_indices={1}))
            job_id = manager.submit(_plan(Path(tmp), video_count=1, existing_file_behavior="ask"))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).pending_conflict is not None))
            snap = manager.get(job_id).snapshot()
            self.assertIn("path", snap["pending_conflict"])
            self.assertEqual(snap["state"], "running")

            # Must resolve before the test ends: an unanswered "ask"
            # blocks its worker thread for CONFLICT_TIMEOUT_SECONDS
            # (600s), and ThreadPoolExecutor's atexit handler waits for
            # every submitted job across every JobManager to finish
            # before the interpreter can exit -- leaving this hanging
            # would stall the whole test process at shutdown, not just
            # this test.
            manager.resolve_conflict(job_id, "skip")
            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED))

    def test_resolve_skip_marks_item_skipped_and_job_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=partial(FakeDownloader, conflict_indices={1}))
            job_id = manager.submit(_plan(Path(tmp), video_count=1, existing_file_behavior="ask"))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).pending_conflict is not None))
            self.assertTrue(manager.resolve_conflict(job_id, "skip"))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED))
            job = manager.get(job_id)
            self.assertIsNone(job.pending_conflict)
            self.assertEqual(job.result.skipped, 1)
            self.assertEqual(job.result.downloaded, 0)

    def test_resolve_overwrite_downloads_the_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=partial(FakeDownloader, conflict_indices={1}))
            job_id = manager.submit(_plan(Path(tmp), video_count=1, existing_file_behavior="ask"))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).pending_conflict is not None))
            self.assertTrue(manager.resolve_conflict(job_id, "overwrite"))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED))
            job = manager.get(job_id)
            self.assertEqual(job.result.downloaded, 1)
            self.assertEqual(job.result.skipped, 0)

    def test_resolve_unknown_job_returns_false(self):
        manager = JobManager(downloader_factory=FakeDownloader)
        self.assertFalse(manager.resolve_conflict("does-not-exist", "skip"))

    def test_resolve_with_no_pending_conflict_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=FakeDownloader)  # no conflicts configured
            job_id = manager.submit(_plan(Path(tmp)))
            _wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED)
            self.assertFalse(manager.resolve_conflict(job_id, "skip"))

    def test_resolve_rejects_invalid_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = JobManager(downloader_factory=partial(FakeDownloader, conflict_indices={1}))
            job_id = manager.submit(_plan(Path(tmp), video_count=1, existing_file_behavior="ask"))
            self.assertTrue(_wait_until(lambda: manager.get(job_id).pending_conflict is not None))
            self.assertFalse(manager.resolve_conflict(job_id, "delete_everything"))
            # The job is still waiting -- the bad action didn't consume the slot.
            self.assertIsNotNone(manager.get(job_id).pending_conflict)
            manager.resolve_conflict(job_id, "skip")  # let it finish for cleanup
            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED))

    def test_unanswered_conflict_times_out_to_skip(self):
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch("app.jobs.CONFLICT_TIMEOUT_SECONDS", 0.05):
            manager = JobManager(downloader_factory=partial(FakeDownloader, conflict_indices={1}))
            job_id = manager.submit(_plan(Path(tmp), video_count=1, existing_file_behavior="ask"))

            self.assertTrue(_wait_until(lambda: manager.get(job_id).state == JobState.COMPLETED, timeout=2))
            job = manager.get(job_id)
            self.assertEqual(job.result.skipped, 1)


if __name__ == "__main__":
    unittest.main()
