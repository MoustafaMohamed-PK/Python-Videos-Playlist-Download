#!/usr/bin/env python3
"""
Entry point for the web UI.

    python webmain.py [--host H] [--port P] [--root DIR] [--config PATH]
    python webmain.py --stop [--port P]     # stop a running instance

Binds to 127.0.0.1 by default. This server has no login, can fetch
whatever URL it's given, and can read/write files under its download
root -- exposing it beyond localhost means anyone who can reach it can
do the same, so --host is an explicit, warned-about opt-in (see
README.md's Security section).

Served through waitress (a pure-Python, threaded WSGI server) rather
than Flask's own development server: a long-lived SSE connection plus
concurrent downloads need real request-level threading, which the dev
server explicitly isn't built to provide.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from app.config import ConfigManager  # noqa: E402
from app.jobs import JobManager  # noqa: E402
from app.utils import setup_logging, use_bundled_ffmpeg  # noqa: E402
from web.app import create_app  # noqa: E402

# Talks only to 127.0.0.1, so ignore any http_proxy/https_proxy settings.
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# How long a shutdown waits for cancelled downloads to wind down before
# exiting anyway.
_SHUTDOWN_GRACE_SECONDS = 5.0


def _local_request(port: int, path: str, method: str = "GET"):
    """Call a running instance on this machine; returns the decoded JSON body.

    Raises urllib.error.URLError when nothing is listening on ``port``.
    """
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        # Mutations must be JSON (see web/security.py), even with no body.
        data=b"{}" if method == "POST" else None,
        headers={"Content-Type": "application/json"},
    )
    with _LOCAL_OPENER.open(request, timeout=5) as response:
        return json.loads(response.read() or b"{}")


def _is_running(port: int) -> bool:
    try:
        _local_request(port, "/api/status")
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def stop_running_instance(port: int) -> int:
    """Implements ``--stop``: ask the instance on ``port`` to exit."""
    try:
        body = _local_request(port, "/api/shutdown", method="POST")
    except urllib.error.HTTPError as exc:
        print(f"The app on port {port} refused to stop (HTTP {exc.code}).", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError):
        print(f"Media Downloader is not running on port {port}.")
        return 1

    cancelled = body.get("cancelled_jobs", 0)
    if cancelled:
        print(f"Cancelled {cancelled} running download(s); partial files will resume next time.")

    # Wait for the port to actually free up, so a script can start a
    # fresh instance straight after this returns.
    deadline = time.monotonic() + _SHUTDOWN_GRACE_SECONDS + 5
    while time.monotonic() < deadline and _is_running(port):
        time.sleep(0.25)
    if _is_running(port):
        print(f"Asked the app on port {port} to stop, but it is still running.", file=sys.stderr)
        return 1
    print(f"Media Downloader on port {port} has stopped.")
    return 0


def _make_shutdown(job_manager: JobManager):
    def shutdown() -> None:
        # Jobs were already told to cancel; give them a moment to stop
        # cleanly (close files, finish an in-progress merge).
        deadline = time.monotonic() + _SHUTDOWN_GRACE_SECONDS
        while job_manager.active_count() and time.monotonic() < deadline:
            time.sleep(0.2)
        print("Media Downloader stopped.", flush=True)
        logging.shutdown()
        # waitress.serve() blocks the main thread with no stop hook, so
        # end the process directly. In a PyInstaller build, the
        # bootloader parent sees this exit and cleans up its temp dir.
        os._exit(0)

    return shutdown


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="webmain.py", description="Run the Media Downloader web UI."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1, localhost only)."
    )
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")
    parser.add_argument(
        "--root", help="Download root directory (default: from config, or ./downloads)."
    )
    parser.add_argument("--config", help="Path to a config JSON file (default: ./config.json).")
    parser.add_argument(
        "--open-browser",
        dest="open_browser",
        action="store_true",
        default=getattr(sys, "frozen", False),
        help=(
            "Open the UI in the default browser once the server starts "
            "(default: on when running as a packaged executable, off when run from source)."
        ),
    )
    parser.add_argument(
        "--no-browser",
        dest="open_browser",
        action="store_false",
        help="Don't open a browser automatically.",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop the Media Downloader already running on --port, then exit.",
    )
    args = parser.parse_args(argv)

    if args.stop:
        return stop_running_instance(args.port)

    browser_url = f"http://127.0.0.1:{args.port}"
    if _is_running(args.port):
        # e.g. the .exe was double-clicked a second time.
        print(f"Media Downloader is already running at {browser_url}")
        print(f"To stop it: use the 'Stop app' button, or run this program with --stop --port {args.port}")
        if args.open_browser:
            webbrowser.open(browser_url)
        return 0

    use_bundled_ffmpeg()
    setup_logging()
    config_manager = ConfigManager(args.config) if args.config else ConfigManager()
    config = config_manager.load()

    root_str = (
        args.root
        or config.web_download_root
        or config.download_folder
        or str(Path.cwd() / "downloads")
    )
    download_root = Path(root_str).expanduser().resolve()
    download_root.mkdir(parents=True, exist_ok=True)

    if args.host not in ("127.0.0.1", "localhost"):
        print(
            f"WARNING: binding to {args.host} exposes an unauthenticated server that can "
            "fetch arbitrary URLs and read files under its download root. Only do this on "
            "a trusted network -- this app has no login.",
            file=sys.stderr,
        )

    job_manager = JobManager(max_workers=2)
    app = create_app(
        download_root=download_root,
        config=config,
        host=args.host,
        port=args.port,
        job_manager=job_manager,
        shutdown=_make_shutdown(job_manager),
    )

    print(f"Media Downloader web UI: http://{args.host}:{args.port}")
    print(f"Download root: {download_root}")

    if args.open_browser:
        # Always open via 127.0.0.1, even if --host binds to 0.0.0.0 -- the
        # browser on this machine can always reach the loopback address.
        threading.Timer(1.0, webbrowser.open, args=[browser_url]).start()

    print("To stop: click 'Stop app' in the page, press Ctrl+C here, close this window,")
    print(f"or run this program again with --stop (add --port {args.port} if you changed it).")

    from waitress import serve

    serve(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
