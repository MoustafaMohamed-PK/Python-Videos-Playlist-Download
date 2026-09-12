# YouTube Video & Playlist Downloader

A cross-platform (Ubuntu/Linux + Windows) command-line application for
downloading YouTube videos and playlists, built on top of
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and FFmpeg.

## What it does

- Downloads a single YouTube video or an entire playlist.
- Lets you pick a quality (4K down to 360p, or audio-only).
- Lets you choose how files are named: original title, sequential
  numbers, or a custom pattern like `lesson_{number}`.
- Lets you choose the destination folder (creating it if needed).
- Shows live download progress (and overall playlist progress).
- Resumes interrupted downloads automatically (via yt-dlp).
- Remembers your preferences in `config.json` for next time.
- Skips, overwrites, or asks about files that already exist.
- Works the same way from an interactive menu or from command-line flags.

## Requirements

- **Python 3.9+**
- **FFmpeg** (system dependency, not a Python package) — required to
  merge separate video/audio streams and to produce audio-only MP3s.
- Internet access to reach YouTube.

## Installation

### Ubuntu / Linux

```bash
# 1. Install FFmpeg
sudo apt update
sudo apt install ffmpeg

# 2. Get the project
cd youtube_downloader

# 3. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Run it
python3 main.py
```

### Windows

```powershell
# 1. Install FFmpeg
#    Easiest via winget:
winget install ffmpeg
#    Or download a build from https://ffmpeg.org/download.html and add
#    its \bin folder to your PATH.

# 2. Get the project
cd youtube_downloader

# 3. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Run it
python main.py
```

Verify FFmpeg is on PATH on either platform with:

```bash
ffmpeg -version
```

If this fails, the app will still run but will warn you before any
download that requires merging separate video/audio streams.

## Interactive usage

Just run the program with no arguments and follow the prompts:

```bash
python main.py          # Windows: python main.py
python3 main.py         # Linux
```

Example flow:

```
========================================
        YouTube Video Downloader
========================================

What do you want to download?
1. Single Video
2. Playlist
Enter your choice: 1

Enter YouTube URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ

Available qualities:
1. Best available
2. 2160p (4K)
3. 1440p
4. 1080p
5. 720p
6. 480p
7. 360p
8. Audio only
Choose quality: 4

How should files be named?
1. Original YouTube title
2. Sequential numbering (1.mp4, 2.mp4, ...)
3. Custom pattern (e.g. lesson_{number})
Choose naming: 1

Enter download folder: ./downloads

========================================
            Download Summary
========================================
Type       : Single Video
Title      : ...
Quality    : 1080p
Naming     : original
Output     : downloads

Start download? [Y/n]:
```

Your answers (quality, folder, naming, existing-file behavior) are saved
to `config.json` and reused as defaults next time.

## CLI (non-interactive) usage

All options are optional; anything you don't pass falls back to your
saved config.

```bash
python main.py --url "https://www.youtube.com/watch?v=..." \
  --quality 1080p \
  --output "./downloads" \
  --name original
```

Playlist example:

```bash
python main.py \
  --url "https://www.youtube.com/playlist?list=XXXX" \
  --quality 1080p \
  --output "./downloads" \
  --pattern "lesson_{number}"
```

### Supported arguments

| Flag           | Description                                                        |
|----------------|---------------------------------------------------------------------|
| `--url`        | YouTube video or playlist URL. Required in non-interactive mode.    |
| `--type`       | `video` or `playlist` (informational; type is auto-detected).       |
| `--quality`    | `best`, `2160p`, `1440p`, `1080p`, `720p`, `480p`, `360p`, `audio`.  |
| `--output`     | Destination folder (created automatically if missing).              |
| `--name`       | `original` or `numbered` filename mode.                             |
| `--pattern`    | Custom filename pattern (implies pattern mode). See below.          |
| `--overwrite`  | `skip`, `overwrite`, or `ask` — behavior for existing files.         |
| `--playlist`   | Force playlist handling (type is normally auto-detected anyway).    |
| `--config`     | Path to an alternate config JSON file.                              |

## Quality selection

The app queries the video's real, available formats and maps your
choice onto a concrete `yt-dlp` format selector. If your chosen quality
isn't actually available for that video, the app tells you clearly and
lists what **is** available — it never silently substitutes a different
resolution.

When the chosen quality requires separate video and audio streams (most
qualities above old-style "progressive" formats), FFmpeg is used to mux
them into a single `.mp4`. Audio-only downloads are extracted to `.mp3`.

## Filename patterns

Choose from three naming modes:

- **Original title** — `Introduction to Python.mp4`
- **Sequential numbering** — `1.mp4`, `2.mp4`, `3.mp4`, ...
- **Custom pattern** — any string using these placeholders:

  | Placeholder        | Meaning                                    |
  |---------------------|---------------------------------------------|
  | `{number}`          | 1-based position (alias of `playlist_index`) |
  | `{playlist_index}`  | 1-based position within a playlist           |
  | `{title}`           | The video's title                            |
  | `{uploader}`        | The channel/uploader name                    |

  Example: pattern `lesson_{number}` → `lesson_1.mp4`, `lesson_2.mp4`, ...

Filenames are sanitized so they're valid on both Windows and Linux
(illegal characters like `: * ? " < > |` are replaced), while Unicode
titles (Arabic, etc.) are preserved.

## Playlist downloads

Playlists are detected automatically from the URL. The app shows the
playlist title and video count, then downloads every video in order,
numbering sequentially if you've chosen numbered or pattern-based
filenames. A failure on one playlist item does **not** stop the rest —
the run finishes and reports downloaded/failed/skipped counts plus which
videos failed and why.

## Existing files

When a target filename already exists, choose:

- **Skip** — leave the existing file alone (default).
- **Overwrite** — replace it.
- **Ask** — you're prompted for each conflicting file.

## Resuming interrupted downloads

If a download is interrupted (network drop, Ctrl+C, etc.), just run the
same command again — `yt-dlp`'s own partial-download tracking resumes
where it left off rather than starting over.

## Configuration

Preferences are stored in `config.json` (see `config.json.example` for
the shape) next to `main.py`:

```json
{
  "download_folder": "",
  "quality": "1080p",
  "filename_mode": "original",
  "filename_pattern": "{title}",
  "existing_file_behavior": "skip"
}
```

No cookies, passwords, or authentication tokens are ever stored in this
file.

## Troubleshooting

- **"FFmpeg was not found"** — Install FFmpeg and make sure it's on your
  PATH (`ffmpeg -version` should work from any terminal).
- **"This video is age-restricted and requires authentication"** — this
  app does not manage login cookies/authentication; age-restricted
  videos requiring sign-in can't be downloaded.
- **"The selected quality is not available"** — pick one of the
  qualities listed in the error message; the app won't silently
  substitute a different resolution.
- **Network/timeout errors** — check your internet connection and retry;
  transient failures don't require restarting the whole playlist.
- **Permission denied writing files** — choose a destination folder your
  user account can write to.

## Running the tests

```bash
python -m unittest discover -s tests -v
```

Tests cover filename generation/sanitization, sequential numbering,
custom patterns, configuration load/save, URL validation, path
handling, and quality/format selection — none require network access or
real downloads (`yt-dlp` network calls are not exercised by these
tests).

## Project structure

```
youtube_downloader/
├── main.py                 # Entry point
├── requirements.txt
├── README.md
├── config.json.example
├── app/
│   ├── __init__.py
│   ├── cli.py               # Menus, argument parsing, orchestration
│   ├── config.py             # Load/save config.json
│   ├── downloader.py          # yt-dlp engine, progress, error handling
│   ├── formats.py             # Quality → yt-dlp format selector logic
│   ├── filename.py             # Filename modes, patterns, sanitization
│   ├── validators.py           # URL / path / input validation
│   └── utils.py                 # FFmpeg detection, formatting, logging
└── tests/
    ├── test_filename.py
    ├── test_config.py
    ├── test_validators.py
    └── test_formats.py
```

## Extending with a GUI later

All user interaction lives in `app/cli.py`; the rest of `app/` (config,
downloader, formats, filename, validators) has no dependency on the
terminal. A future GUI can reuse those modules directly and only needs
to replace `cli.py`'s prompts/printing with widget callbacks.

## Security notes

- No `eval()`/`exec()`, no shell string construction, no SSL verification
  disabling.
- Credentials/cookies are never collected, stored, or logged.
- Filenames are sanitized before being used as paths, and downloads are
  always written under the user-selected destination folder.