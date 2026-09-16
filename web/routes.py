"""
API endpoints for the web UI.

Responsible for:
    - Translating HTTP requests into calls on app.service (the same
      analyze/plan/execute pipeline the CLI uses) and app.jobs
      (background execution + progress).
    - Resolving a destination two ways: a "subfolder" string confined
      to the configured download root (app.paths.resolve_within), or a
      "destination_path" the client supplies directly -- validated the
      same way the CLI validates a typed path
      (app.validators.validate_destination_path), but NOT confined to
      any root. That second mode is a deliberate choice: this is a
      single-user, localhost-only tool, and being able to pick any
      folder on the machine (via the browse endpoints below, or by
      typing a path) was requested explicitly, matching what the CLI
      already allows. See README.md's Security section for the
      tradeoff this implies for the file-serving endpoint below.
    - Browsing the server's own filesystem (GET /api/browse, POST
      /api/browse/mkdir) so the UI can offer a folder picker instead of
      only a text field -- deliberately NOT confined to the download
      root, for the same reason "destination_path" isn't.
    - Serving finished files back to the browser by job id + index,
      never by a client-supplied path.
    - Relaying an "ask" existing-file conflict from a running job to
      the browser and back (GET job snapshot carries
      "pending_conflict"; POST /api/jobs/<id>/resolve answers it).
    - Stopping the whole app (POST /api/shutdown), for the UI's
      "Stop app" button and `--stop` on the command line.

Nothing here talks to yt-dlp directly; all of that stays in
app.downloader/app.service, so this module and the CLI can never
implement the download pipeline differently from each other.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from queue import Empty

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from app.downloader import DownloadAppError
from app.filename import sanitize_filename
from app.jobs import JobManager
from app.paths import resolve_within
from app.service import DownloadRequest, QualityUnavailableError, analyze, plan
from app.sites import match_extractor
from app.validators import ValidationError, validate_destination_path

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


@bp.get("/api/settings")
def api_settings():
    settings = dict(_default_settings())
    settings["download_root"] = str(_download_root())
    return jsonify(settings)


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
    duration = analysis.videos[0].duration if (not analysis.is_playlist and analysis.videos) else None

    return jsonify(
        {
            "url": analysis.url,
            "title": analysis.title,
            "is_playlist": analysis.is_playlist,
            "item_count": len(analysis.videos),
            "site": site.display_name or site.extractor,
            "thumbnail": analysis.thumbnail,
            "duration": duration,
            "qualities": [{"key": o.key, "label": o.label} for o in analysis.quality_menu],
            "subtitles": [{"lang": o.lang, "label": o.label} for o in analysis.subtitle_menu],
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

    subtitle_langs_raw = data.get("subtitle_langs") or []
    if not isinstance(subtitle_langs_raw, list):
        return jsonify(error="subtitle_langs must be a list of language codes."), 400
    subtitle_langs = [str(lang).strip() for lang in subtitle_langs_raw if str(lang).strip()]
    subtitles_only = bool(data.get("subtitles_only"))
    if subtitles_only and not subtitle_langs:
        return jsonify(error="subtitles_only requires at least one subtitle language."), 400

    manager = _job_manager()
    analysis = manager.cached_analysis(url)
    if analysis is None:
        try:
            analysis = analyze(url)
        except (DownloadAppError, ValidationError) as exc:
            return jsonify(error=str(exc)), 400
        manager.cache_analysis(url, analysis)

    destination_path = (data.get("destination_path") or "").strip()
    if destination_path:
        # A directly-supplied path (typed, or picked via the browse
        # endpoints below) -- validated like the CLI validates a typed
        # path, but not confined to any root. See the module docstring.
        try:
            destination = validate_destination_path(destination_path)
        except ValidationError as exc:
            return jsonify(error=str(exc)), 400
    else:
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
        subtitle_langs=subtitle_langs,
        subtitles_only=subtitles_only,
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


@bp.post("/api/jobs/<job_id>/resolve")
def api_resolve_job_conflict(job_id: str):
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if not _job_manager().resolve_conflict(job_id, action):
        return jsonify(error="No pending conflict for this job, or an invalid action."), 409
    return jsonify(resolved=True), 202


@bp.get("/api/jobs/<job_id>/files/<int:index>")
def api_get_job_file(job_id: str, index: int):
    job = _job_manager().get(job_id)
    if job is None or job.result is None:
        return jsonify(error="Job not found."), 404

    match = next((r for r in job.result.results if r.index == index), None)
    if match is None or not match.success or match.output_path is None:
        return jsonify(error="File not found."), 404

    # NOT confined to the download root: since a job's destination can
    # now be any path the user typed or browsed to (see the module
    # docstring), a legitimate download can legitimately live outside
    # it. This is still safe to serve because output_path was never
    # client-supplied at request time -- it was produced exclusively
    # by our own Downloader while running this exact job, addressed
    # here only by an unguessable job id (a server-generated UUID) plus
    # an index into that job's own completed results.
    resolved = Path(match.output_path).resolve()
    if not resolved.is_file():
        return jsonify(error="File not found."), 404

    return send_file(resolved, as_attachment=True, download_name=resolved.name)


@bp.get("/api/browse")
def api_browse():
    """List subdirectories of a filesystem path, for the folder-picker UI.

    Deliberately not confined to the download root -- matches
    "destination_path" above. Defaults to the user's home directory
    when no path is given, since that's a more useful starting point
    than the filesystem root for picking a download folder.
    """
    raw_path = (request.args.get("path") or "").strip() or str(Path.home())
    try:
        target = Path(raw_path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return jsonify(error="Invalid path."), 400

    if not target.exists():
        return jsonify(error="That path does not exist."), 404
    if not target.is_dir():
        return jsonify(error="That path is not a directory."), 400

    directories = []
    try:
        for entry in target.iterdir():
            try:
                if entry.is_dir():
                    directories.append(entry.name)
            except OSError:
                continue  # permission denied, broken symlink, etc. -- skip silently
    except OSError as exc:
        return jsonify(error=f"Could not list directory: {exc}"), 400
    directories.sort(key=str.lower)

    parent = str(target.parent) if target.parent != target else None
    return jsonify(path=str(target), parent=parent, directories=directories)


@bp.post("/api/browse/mkdir")
def api_browse_mkdir():
    data = request.get_json(silent=True) or {}
    parent_str = (data.get("path") or "").strip()
    name = (data.get("name") or "").strip()
    if not parent_str or not name:
        return jsonify(error="path and name are required."), 400

    try:
        parent = Path(parent_str).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return jsonify(error="Invalid path."), 400
    if not parent.is_dir():
        return jsonify(error="Parent is not a directory."), 400

    safe_name = sanitize_filename(name)
    new_dir = parent / safe_name
    try:
        new_dir.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        return jsonify(error=f"Could not create folder: {exc}"), 400

    return jsonify(path=str(new_dir)), 201


@bp.get("/api/status")
def api_status():
    return jsonify(active_jobs=_job_manager().active_count())


@bp.post("/api/shutdown")
def api_shutdown():
    """Stop the whole app (the "Stop app" button, and `webmain.py --stop`).

    Covered by the same Host-allowlist and JSON-only checks as every
    other mutation (web/security.py), so a random web page can't
    trigger it. Running jobs are cancelled first; their partial files
    stay on disk and resume next time.
    """
    shutdown = current_app.extensions.get("shutdown")
    if shutdown is None:
        return jsonify(error="Shutdown is not available."), 404

    cancelled = _job_manager().cancel_all()
    # Delay so this response is sent before the process goes away.
    timer = threading.Timer(0.5, shutdown)
    timer.daemon = True
    timer.start()
    return jsonify(stopping=True, cancelled_jobs=cancelled), 202


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
