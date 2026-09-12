#!/usr/bin/env python3
"""
YouTube Video & Playlist Downloader — entry point.

Interactive usage:
    python main.py            (Linux/macOS: python3 main.py)

Non-interactive usage:
    python main.py --url "https://www.youtube.com/watch?v=..." \\
        --quality 1080p --output "./downloads" --name original

See README.md for the full list of options and examples.
"""

import sys
from pathlib import Path

# Ensure the project root is importable regardless of the current working
# directory the script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
