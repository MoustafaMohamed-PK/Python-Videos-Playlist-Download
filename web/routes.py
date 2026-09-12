"""
API endpoints for the web UI.

Responsible for:
    - Translating HTTP requests into calls on app.service (the same
      analyze/plan/execute pipeline the CLI uses) and app.jobs
      (background execution + progress).
    - Confining every destination path to the configured download
      root via app.paths.resolve_within -- the browser can supply a
      "subfolder" string, never an absolute path.
    - Serving finished files back to the browser by job id + index,
      never by a client-supplied path.

Nothing here talks to yt-dlp directly; all of that stays in
app.downloader/app.service, so this module and the CLI can never
implement the download pipeline differently from each other.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from queue import Empty

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from app.downloader import DownloadAppError
from app.jobs import JobManager
from app.paths import resolve_within
from app.service import DownloadRequest, QualityUnavailableError, analyze, plan
from app.sites import match_extractor
from app.validators import ValidationError

bp = Blueprint("api", __name__)


def _job_manager() -> JobManager:
    return current_app.extensions["job_manager"]


def _download_root() -> Path:
    return current_app.extensions["download_root"]


def _default_settings() -> dict:
    return current_app.extensions["default_settings"]


@bp.get("/")
def index():
    from flask import render_template

    return render_template("index.html")


@bp.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="A URL is required."), 400

    try:
        analysis = analyze(url)
    except (DownloadAppError, ValidationError) as exc:
        return jsonify(error=str(exc)), 400

    _job_manager().cache_analysis(url, analysis)

    site = match_extractor(analysis.url)
    thumbnail = None
    if analysis.videos:
        raw = analysis.videos[0].raw or {}
        thumbnail = raw.get("thumbnail")
    duration = analysis.videos[0].duration if (not analysis.is_playlist and analysis.videos) else None

    return jsonify(
        {
            "url": analysis.url,
            "title": analysis.title,
            "is_playlist": analysis.is_playlist,
            "item_count": len(analysis.videos),
            "site": site.display_name or site.extractor,
            "thumbnail": thumbnail,
            "duration": duration,
            "qualities": [{"key": o.key, "label": o.label} for o in analysis.quality_menu],
            "warnings": analysis.warnings,
        }
    )


@bp.post("/api/jobs")
def api_create_job():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="A URL is required."), 400

    quality_label = data.get("quality") or _default_settings()["quality"]
    filename_mode = data.get("filename_mode") or _default_settings()["filename_mode"]
    filename_pattern = data.get("filename_pattern")
    existing_file_behavior = data.get("existing_file_behavior") or "skip"
    concurrency = data.get("concurrency") or _default_settings()["concurrency"]
    concurrent_fragments = _default_settings()["concurrent_fragments"]

    try:
        concurrency = int(concurrency)
    except (TypeError, ValueError):
        return jsonify(error="concurrency must be an integer."), 400

    manager = _job_manager()
    analysis = manager.cached_analysis(url)
    if analysis is None:
        try:
            analysis = analyze(url)
        except (DownloadAppError, ValidationError) as exc:
            return jsonify(error=str(exc)), 400
        manager.cache_analysis(url, analysis)

    try:
        destination = resolve_within(_download_root(), data.get("subfolder"))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400

    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return jsonify(error=f"Could not create destination folder: {exc}"), 400

    download_request = DownloadRequest(
        quality_label=quality_label,
        destination=destination,
        filename_mode=filename_mode,
        filename_pattern=filename_pattern,
        existing_file_behavior=existing_file_behavior,
        concurrency=concurrency,
        concurrent_fragments=concurrent_fragments,
    )

    try:
        run_plan = plan(download_request, analysis)
    except QualityUnavailableError as exc:
        return (
            jsonify(
                error=str(exc),
                qualities=[{"key": o.key, "label": o.label} for o in exc.menu],
            ),
            400,
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    job_id = manager.submit(run_plan)
    return jsonify(job_id=job_id), 202


@bp.get("/api/jobs")
def api_list_jobs():
    return jsonify([job.snapshot() for job in _job_manager().list()])


@bp.get("/api/jobs/<job_id>")
def api_get_job(job_id: str):
    job = _job_manager().get(job_id)
    if job is None:
        return jsonify(error="Job not found."), 404
    return jsonify(job.snapshot())


@bp.post("/api/jobs/<job_id>/cancel")
def api_cancel_job(job_id: str):
    if not _job_manager().cancel(job_id):
        return jsonify(error="Job not found."), 404
    return jsonify(cancelled=True), 202


@bp.get("/api/jobs/<job_id>/files/<int:index>")
def api_get_job_file(job_id: str, index: int):
    job = _job_manager().get(job_id)
    if job is None or job.result is None:
        return jsonify(error="Job not found."), 404

    match = next((r for r in job.result.results if r.index == index), None)
    if match is None or not match.success or match.output_path is None:
        return jsonify(error="File not found."), 404

    # Re-validate against the download root even though this path was
    # produced by our own Downloader -- never trust a stored path
    # without re-checking it stays inside the root before serving it
    # back over HTTP.
    root = _download_root().resolve()
    resolved = Path(match.output_path).resolve()
    if root != resolved and root not in resolved.parents:
        return jsonify(error="File not found."), 404
    if not resolved.is_file():
        return jsonify(error="File not found."), 404

    return send_file(resolved, as_attachment=True, download_name=resolved.name)


@bp.get("/api/events")
def api_events():
    manager = _job_manager()

    def generate():
        queue = manager.subscribe()
        try:
            last_keepalive = time.monotonic()
            while True:
                try:
                    payload = queue.get(timeout=1.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except Empty:
                    pass
                now = time.monotonic()
                if now - last_keepalive > 15:
                    yield ": keepalive\n\n"
                    last_keepalive = now
        finally:
            manager.unsubscribe(queue)

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
