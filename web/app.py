"""
Flask application factory for the web UI.

Responsible for:
    - Wiring together the JobManager, the configured download root, and
      default settings into one Flask app.
    - Installing the security checks (Host allowlist, JSON-only
      mutations) from web.security.
    - Registering the API blueprint from web.routes.

Deliberately NOT responsible for how the app is served -- webmain.py
decides that (waitress, bound to 127.0.0.1 by default).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from flask import Flask

from app.config import AppConfig
from app.jobs import JobManager
from web.routes import bp
from web.security import install_security_checks


def create_app(
    download_root: Path,
    config: AppConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    job_manager: Optional[JobManager] = None,
) -> Flask:
    app = Flask(__name__)
    app.extensions["job_manager"] = job_manager or JobManager(max_workers=2)
    app.extensions["download_root"] = download_root
    app.extensions["default_settings"] = {
        "quality": config.quality,
        "filename_mode": config.filename_mode,
        "concurrency": config.concurrency,
        "concurrent_fragments": config.concurrent_fragments,
    }

    if host in ("127.0.0.1", "localhost"):
        install_security_checks(app, {f"127.0.0.1:{port}", f"localhost:{port}"})
    # else: an explicit opt-in to bind elsewhere (e.g. 0.0.0.0 for LAN
    # access) means the real Host header clients send can't be known
    # in advance, so the allowlist check is skipped for that case --
    # webmain.py prints a loud warning when this happens. Not a
    # supported/hardened configuration; the default (localhost-only)
    # is the one this app is designed around.

    app.register_blueprint(bp)
    return app
