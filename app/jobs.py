"""
Background job registry for running downloads outside an HTTP request.

Responsible for:
    - Running app.service.execute() on a worker thread per job, so an
      HTTP request can return immediately with a job id instead of
      blocking for the whole download.
    - Tracking each job's state and a progress snapshot that a
      reconnecting client can fetch (GET /api/jobs/<id>) instead of
      only being able to watch it live.
    - Fanning progress out to any number of live subscribers (the SSE
      endpoint) via small bounded queues, without ever blocking the
      download worker thread on a slow or disconnected client -- if a
      subscriber's queue fills up, the oldest queued update is dropped
      rather than stalling the download. This is intentionally lossy:
      correctness comes from snapshot(), not from every event reaching
      every subscriber.
    - A short-TTL cache of AnalyzeResult by URL, so a client that just
      analyzed a URL (to show the quality menu) doesn't pay for a
      second extraction moments later when it starts the job.

Thread-safety: all mutable state lives under one RLock.
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from queue import Empty, Full, Queue
from typing import Any, Dict, List, Optional

from app.downloader import DownloadRunResult, Downloader, ProgressEvent
from app.progress import ProgressAggregator
from app.service import AnalyzeResult, DownloaderFactory, RunPlan, execute

ANALYZE_CACHE_TTL_SECONDS = 300

# How long an "ask" conflict waits for a browser response before
# defaulting to "skip" (the safer of the two choices) so a forgotten
# tab can never wedge a job open forever.
CONFLICT_TIMEOUT_SECONDS = 600


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    plan: RunPlan
    state: JobState = JobState.QUEUED
    created_at: float = field(default_factory=time.time)
    error: Optional[str] = None
    result: Optional[DownloadRunResult] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    aggregator: Optional[ProgressAggregator] = None
    # Set while a conflict is awaiting a browser response ("skip" or
    # "overwrite" for an already-existing file); consumed by
    # JobManager.resolve_conflict(). Only one conflict is tracked at a
    # time per job -- see the concurrency note in app/service.py::plan.
    pending_conflict: Optional[Dict[str, Any]] = None
    conflict_queue: Optional[Queue] = None

    def snapshot(self) -> Dict[str, Any]:
        prog = self.aggregator.snapshot() if self.aggregator else None
        return {
            "id": self.id,
            "state": self.state.value,
            "title": self.plan.title,
            "thumbnail": self.plan.thumbnail,
            "is_playlist": self.plan.is_playlist,
            "video_count": self.plan.video_count,
            "created_at": self.created_at,
            "error": self.error,
            "pending_conflict": self.pending_conflict,
            "progress": (
                {
                    "completed": prog.completed,
                    "total": prog.total,
                    "overall_fraction": prog.overall_fraction,
                    "active_count": prog.active_count,
                    "total_speed": prog.total_speed,
                    "downloaded_bytes": prog.downloaded_bytes,
                    "total_bytes": prog.total_bytes,
                    "eta": prog.eta,
                }
                if prog
                else None
            ),
            "results": [
                {
                    "index": r.index,
                    "title": r.title,
                    "success": r.success,
                    "skipped": r.skipped,
                    "error": r.error,
                    "warning": r.warning,
                    "has_file": r.output_path is not None,
                }
                for r in (self.result.results if self.result else [])
            ],
        }


class JobManager:
    """Owns the job registry, worker pool, subscriber fan-out, and analyze cache."""

    def __init__(
        self,
        max_workers: int = 2,
        history_limit: int = 100,
        downloader_factory: DownloaderFactory = Downloader,
    ):
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._history_limit = history_limit
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        # One global feed, not one per job: the web UI opens a single
        # SSE connection for the whole page (browsers cap concurrent
        # HTTP/1.1 connections per origin at ~6) and every job's
        # updates are broadcast to it, each payload carrying its own
        # job "id" so the client can route it.
        self._subscribers: List[Queue] = []
        self._analyze_cache: Dict[str, Any] = {}  # url -> (AnalyzeResult, expiry_time)
        self._downloader_factory = downloader_factory

    # -- analyze cache -----------------------------------------------

    def cached_analysis(self, url: str) -> Optional[AnalyzeResult]:
        with self._lock:
            entry = self._analyze_cache.get(url)
            if entry is None:
                return None
            analysis, expiry = entry
            if time.time() > expiry:
                del self._analyze_cache[url]
                return None
            return analysis

    def cache_analysis(self, url: str, analysis: AnalyzeResult) -> None:
        with self._lock:
            self._analyze_cache[url] = (analysis, time.time() + ANALYZE_CACHE_TTL_SECONDS)

    # -- job lifecycle -------------------------------------------------

    def submit(self, run_plan: RunPlan) -> str:
        job_id = uuid.uuid4().hex
        job = Job(id=job_id, plan=run_plan, aggregator=ProgressAggregator(total=run_plan.video_count))
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._trim_history()
        self._executor.submit(self._run, job)
        return job_id

    def _trim_history(self) -> None:
        # Only ever drops jobs that are done -- never the ones still
        # queued/running, however old, since the caller can't retrieve
        # their result any other way.
        i = 0
        while len(self._order) > self._history_limit and i < len(self._order):
            candidate_id = self._order[i]
            candidate = self._jobs.get(candidate_id)
            if candidate is None or candidate.state in (
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
            ):
                self._order.pop(i)
                self._jobs.pop(candidate_id, None)
            else:
                i += 1

    def _run(self, job: Job) -> None:
        with self._lock:
            job.state = JobState.RUNNING
        self._publish(job.snapshot())

        def progress_callback(event: ProgressEvent) -> None:
            job.aggregator.update(event)
            self._publish(job.snapshot())

        def ask_overwrite_callback(path_str: str) -> str:
            # Called synchronously from the download worker thread when
            # an item's target file already exists and the job asked
            # for interactive "ask" behavior. Blocks that thread (never
            # the whole server -- each job runs on its own worker) until
            # resolve_conflict() delivers an answer via the queue, or
            # the timeout elapses.
            answer_queue: "Queue[str]" = Queue(maxsize=1)
            with self._lock:
                job.pending_conflict = {"path": path_str}
                job.conflict_queue = answer_queue
            self._publish(job.snapshot())
            try:
                answer = answer_queue.get(timeout=CONFLICT_TIMEOUT_SECONDS)
            except Empty:
                answer = "skip"
            with self._lock:
                job.pending_conflict = None
                job.conflict_queue = None
            self._publish(job.snapshot())
            return answer

        try:
            result = execute(
                job.plan,
                progress_callback=progress_callback,
                cancel_event=job.cancel_event,
                ask_overwrite_callback=ask_overwrite_callback,
                downloader_factory=self._downloader_factory,
            )
            with self._lock:
                job.result = result
                job.state = JobState.CANCELLED if job.cancel_event.is_set() else JobState.COMPLETED
        except Exception as exc:  # noqa: BLE001 -- a worker thread must never crash silently
            with self._lock:
                job.error = str(exc)
                job.state = JobState.FAILED
        self._publish(job.snapshot())

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> List[Job]:
        with self._lock:
            return [self._jobs[jid] for jid in reversed(self._order) if jid in self._jobs]

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        job.cancel_event.set()
        return True

    def active_count(self) -> int:
        """Number of jobs still queued or running."""
        with self._lock:
            return sum(
                1
                for job in self._jobs.values()
                if job.state in (JobState.QUEUED, JobState.RUNNING)
            )

    def cancel_all(self) -> int:
        """Signal every queued/running job to stop; returns how many were signalled.

        Used when the app is shutting down. Interrupted downloads keep
        their partial files, so yt-dlp resumes them on the next run.
        """
        with self._lock:
            active = [
                job
                for job in self._jobs.values()
                if job.state in (JobState.QUEUED, JobState.RUNNING)
            ]
        for job in active:
            job.cancel_event.set()
        return len(active)

    def resolve_conflict(self, job_id: str, action: str) -> bool:
        """Answer a job's pending existing-file conflict.

        Returns False if the job doesn't exist, isn't currently
        waiting on a conflict, or ``action`` isn't "skip"/"overwrite".
        """
        if action not in ("skip", "overwrite"):
            return False
        job = self.get(job_id)
        if job is None:
            return False
        with self._lock:
            queue = job.conflict_queue
        if queue is None:
            return False
        try:
            queue.put_nowait(action)
            return True
        except Full:
            return False

    # -- progress fan-out (SSE) ----------------------------------------

    def subscribe(self) -> "Queue[Dict[str, Any]]":
        q: "Queue[Dict[str, Any]]" = Queue(maxsize=64)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "Queue[Dict[str, Any]]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _publish(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(payload)
            except Full:
                try:
                    q.get_nowait()  # drop the oldest queued update
                except Empty:
                    pass
                try:
                    q.put_nowait(payload)
                except Full:
                    pass  # a burst raced us; this update is skippable
