#!/usr/bin/env python3
"""
Entry point for the web UI.

    python webmain.py [--host H] [--port P] [--root DIR] [--config PATH]

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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from app.config import ConfigManager  # noqa: E402
from app.utils import setup_logging  # noqa: E402
from web.app import create_app  # noqa: E402


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
    args = parser.parse_args(argv)

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

    app = create_app(download_root=download_root, config=config, host=args.host, port=args.port)

    print(f"Media Downloader web UI: http://{args.host}:{args.port}")
    print(f"Download root: {download_root}")

    from waitress import serve

    serve(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
