#!/usr/bin/env python3
"""
Media Downloader — CLI entry point (any site yt-dlp supports).

Interactive usage:
    python main.py            (Linux/macOS: python3 main.py)

Non-interactive usage:
    python main.py --url "https://www.youtube.com/watch?v=..." \\
        --quality 1080p --output "./downloads" --name original

See README.md for the full list of options and examples, and
webmain.py for the browser UI.
"""

import sys
from pathlib import Path

# Ensure the project root is importable regardless of the current working
# directory the script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.cli import main  # noqa: E402
from app.utils import use_bundled_ffmpeg  # noqa: E402

if __name__ == "__main__":
    # A Windows console on a legacy code page (e.g. cp1252) can't encode
    # every video title; print a placeholder instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    use_bundled_ffmpeg()
    sys.exit(main())
