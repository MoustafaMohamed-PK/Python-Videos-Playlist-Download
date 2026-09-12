# Media Downloader

A cross-platform (Ubuntu/Linux + Windows) application for downloading
videos and playlists from any site [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
supports (YouTube, Vimeo, SoundCloud, and ~1700 others), built on
`yt-dlp` and FFmpeg. Usable as a command-line tool or through a local
browser UI — both share the exact same download engine.

## What it does

- Downloads a single video or an entire playlist from any site yt-dlp
  recognizes — run `yt-dlp --list-extractors` for the full list.
- Builds the quality menu from what the site *actually* offers (not a
  fixed YouTube-shaped list), so odd resolutions, audio-only sites, and
  single-format sites all work correctly.
- Lets you choose how files are named: original title, sequential
  numbers, or a custom pattern like `lesson_{number}`.
- Lets you choose the destination folder (creating it if needed).
- Downloads playlist items in parallel (configurable) for faster runs,
  with live per-item and overall progress.
- Resumes interrupted downloads automatically (via yt-dlp).
- Remembers your preferences in `config.json` for next time.
- Skips, overwrites, or asks about files that already exist.
- Works the same way from an interactive menu, command-line flags, or
  a browser (`webmain.py`).

## Requirements

- **Python 3.9+**
- **FFmpeg** (system dependency, not a Python package) — required to
  merge separate video/audio streams and to produce audio-only MP3s.
- Internet access to reach whichever site you're downloading from.

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
python3 main.py           # CLI
python3 webmain.py        # or the web UI (http://127.0.0.1:8765)
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
python main.py             # CLI
python webmain.py          # or the web UI (http://127.0.0.1:8765)
```

Verify FFmpeg is on PATH on either platform with:

```bash
ffmpeg -version
```

If this fails, the app will still run but will warn you before any
download that requires merging separate video/audio streams.

## Interactive CLI usage

Just run the program with no arguments and follow the prompts:

```bash
python main.py          # Windows: python main.py
python3 main.py         # Linux
```

Example flow (quality options reflect this specific video's real
formats, not a fixed list):

```
========================================
            Media Downloader
========================================

Enter video or playlist URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ

Available qualities:
1. Best available
2. 1080p
3. 720p
4. 480p
5. 360p
6. Audio only
Choose quality: 2

How should files be named?
1. Original title
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

Playlist example, downloading 4 items in parallel:

```bash
python main.py \
  --url "https://www.youtube.com/playlist?list=XXXX" \
  --quality 1080p \
  --output "./downloads" \
  --pattern "lesson_{number}" \
  --concurrency 4
```

Any other supported site works the same way:

```bash
python main.py --url "https://vimeo.com/..." --quality best --output "./downloads"
python main.py --url "https://soundcloud.com/artist/track" --quality audio --output "./downloads"
```

### Supported arguments

| Flag            | Description                                                          |
|-----------------|-----------------------------------------------------------------------|
| `--url`         | Video or playlist URL (any site yt-dlp supports). Required in non-interactive mode. |
| `--quality`     | `best`, `audio`, or a resolution like `1080p`/`720p`/`540p` — whatever the site actually offers, not a fixed list. |
| `--output`      | Destination folder (created automatically if missing).                |
| `--name`        | `original` or `numbered` filename mode.                               |
| `--pattern`     | Custom filename pattern (implies pattern mode). See below.            |
| `--overwrite`   | `skip`, `overwrite`, or `ask` — behavior for existing files.           |
| `--playlist`    | Force playlist handling (type is normally auto-detected anyway).      |
| `--concurrency` | Playlist items to download in parallel, 1-8 (default: from config, normally 3). |
| `--config`      | Path to an alternate config JSON file.                                |

## Quality selection

The app builds the quality menu from the video's real, available
formats — for a single video this is queried directly; for a playlist
item (where formats aren't known until each item is fetched) it falls
back to a standard resolution ladder and reports what it actually got.
If your chosen quality isn't available for a given video, the app
tells you clearly and lists what **is** available — it never silently
substitutes a different resolution.

When the chosen quality requires separate video and audio streams,
FFmpeg is used to mux them. On sites that offer H.264/AAC (most video
sites, including YouTube), that combination is preferred over
newer codecs like AV1/VP9 for playback compatibility with common video
players, and merged into `.mp4`. On webm/vp9/opus-only sites, the app
doesn't force an incompatible mp4 remux — it lets the container follow
the codecs actually available. Audio-only downloads are extracted to
`.mp3` regardless of source format.

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

Playlists are detected automatically from the URL, on any supported
site. The app shows the playlist title and video count, then downloads
every video — in parallel if `--concurrency`/the web UI's concurrency
setting is above 1 — numbering sequentially if you've chosen numbered
or pattern-based filenames. A failure on one playlist item does **not**
stop the rest — the run finishes and reports downloaded/failed/skipped
counts plus which videos failed and why, in original playlist order
regardless of which items finished first.

## Existing files

When a target filename already exists (in whatever container format
was actually downloaded — not assumed to be `.mp4`), choose:

- **Skip** — leave the existing file alone (default).
- **Overwrite** — replace it.
- **Ask** — you're prompted for each conflicting file (CLI only).

## Resuming interrupted downloads

If a download is interrupted (network drop, Ctrl+C, etc.), just run the
same command again — `yt-dlp`'s own partial-download tracking resumes
where it left off rather than starting over.

## Web UI

```bash
python webmain.py                 # http://127.0.0.1:8765, downloads to ./downloads
python webmain.py --root ~/Videos --port 9000
```

Paste a URL, review the title/thumbnail/duration/site and the real
quality options, pick a subfolder and naming mode, and start the
download. Progress streams live (overall and, for a playlist, each
item), and finished files are downloaded straight from the page.
Reloading the page picks up any job still running or already finished.

`--host`/`--port`/`--root`/`--config` mirror the CLI's `--config` and
let you change the bind address, port, and download root. See
**Security** below before binding anywhere other than `127.0.0.1`.

## Configuration

Preferences are stored in `config.json` (see `config.json.example` for
the shape) next to `main.py`, shared by both the CLI and the web UI:

```json
{
  "download_folder": "",
  "quality": "1080p",
  "filename_mode": "original",
  "filename_pattern": "{title}",
  "existing_file_behavior": "skip",
  "concurrency": 3,
  "concurrent_fragments": 4,
  "web_download_root": ""
}
```

`concurrency` is how many playlist items download at once (1-8).
`concurrent_fragments` is yt-dlp's own within-one-item DASH/HLS
fragment parallelism, unrelated to playlist-level concurrency.
`web_download_root` is the base directory the web UI is confined to
(falls back to `download_folder`, then `./downloads`, if unset).

No cookies, passwords, or authentication tokens are ever stored in this
file.

## Security

The web UI is a convenience layer with **no login** — anyone who can
reach it can make this machine fetch an arbitrary URL and can read
whatever it downloads. This is manageable for a tool that only listens
on `127.0.0.1`, which is why that's the default and the only configuration
this app is designed and hardened around:

- **Binds to `127.0.0.1` by default.** `--host` to bind elsewhere (e.g.
  for LAN access) is an explicit opt-in that prints a warning at
  startup and is not a supported, hardened configuration — there's no
  authentication layer to add on top of it.
- **The browser can never specify an absolute path.** The web UI only
  accepts a "subfolder" string, confined to the configured download
  root by `app/paths.py::resolve_within`: absolute paths and
  backslashes are rejected, `..` segments are dropped rather than
  honored (so an attempt to climb out just lands deeper inside the
  root instead), and the check happens after resolving symlinks so an
  in-tree symlink can't be used to escape it either.
- **Files are served by job + index, never by path** — the download
  endpoint looks up a completed result and re-validates it's still
  inside the download root before sending it, rather than trusting a
  client-supplied filename.
- **CSRF / DNS rebinding**: every mutating request must declare
  `Content-Type: application/json` (a plain HTML form can't set that,
  and setting it from cross-origin JavaScript triggers a CORS
  preflight this server never answers, so the browser blocks the
  actual request), and the `Host` header must match the server's own
  bind address. Together these block both a classic form-based
  CSRF attempt and DNS rebinding from another site the browser has
  open.
- **This app is an arbitrary-URL fetcher by design** — that's the
  feature, not a bug to patch over with a domain allowlist (which
  would defeat the point of supporting "any site yt-dlp knows"). If you
  ever bind this somewhere other than `127.0.0.1`, understand that
  tradeoff explicitly.
- No `eval()`/`exec()`, no shell string construction (yt-dlp invokes
  FFmpeg itself via an argv list, and this app adds no subprocess calls
  of its own), no SSL verification disabling.
- Credentials/cookies are never collected, stored, or logged.

## Troubleshooting

- **"FFmpeg was not found"** — Install FFmpeg and make sure it's on your
  PATH (`ffmpeg -version` should work from any terminal).
- **"No supported site recognizes this URL"** — the URL didn't match
  any of yt-dlp's site-specific extractors, and yt-dlp's generic
  fallback (which handles many smaller sites) didn't match either. Run
  `yt-dlp --list-extractors` to check what's supported.
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

Tests cover filename generation/sanitization, configuration load/save,
site/URL validation, path confinement (including a symlink-escape
attempt), quality/format selection, the analyze/plan/execute service
layer, playlist concurrency and cancellation, and the web API's
security checks and full request flow — none require network access or
real downloads (`yt-dlp` network calls are not exercised by these
tests; the download engine is exercised through hand-written fakes).

## Project structure

```
youtube_downloader/
├── main.py                  # CLI entry point
├── webmain.py                # Web UI entry point
├── requirements.txt
├── README.md
├── config.json.example
├── app/
│   ├── __init__.py
│   ├── cli.py                 # CLI menus, argument parsing, printing
│   ├── service.py               # analyze/plan/execute -- shared by CLI and web
│   ├── jobs.py                   # Background job manager for the web UI
│   ├── paths.py                    # Confines web-supplied paths to a root dir
│   ├── progress.py                  # Thread-safe progress aggregation
│   ├── sites.py                      # Site/URL detection via yt-dlp's extractors
│   ├── config.py                    # Load/save config.json
│   ├── downloader.py               # yt-dlp engine, progress, error handling
│   ├── formats.py                  # Quality menu + yt-dlp format selector logic
│   ├── filename.py                 # Filename modes, patterns, sanitization
│   ├── prompts.py                  # Blocking input() helpers (CLI only)
│   ├── validators.py               # Path / input validation
│   └── utils.py                    # FFmpeg detection, formatting, logging
├── web/
│   ├── app.py                # Flask app factory
│   ├── routes.py               # API endpoints
│   ├── security.py              # Host allowlist + JSON-only mutation checks
│   ├── templates/index.html
│   └── static/{app.js,style.css}
└── tests/
    ├── fakes.py                # Hand-written test doubles (no mocking framework)
    └── test_*.py
```

## Extending further

`app/service.py` (`analyze`/`plan`/`execute`) is the one place the
download pipeline lives — both `app/cli.py` and `web/routes.py` call
into it and never implement download logic themselves. A future
interface (a desktop GUI, a different API shape) should do the same:
call `app.service`, not `app.downloader` directly.
