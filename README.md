# Media Downloader

A cross-platform (Ubuntu/Linux + Windows) application for downloading
videos and playlists from any site [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
supports (YouTube, Vimeo, SoundCloud, and ~1700 others), built on
`yt-dlp` and FFmpeg. Usable as a command-line tool or through a local
browser UI — both share the exact same download engine.

## Contents

- [How it works](#how-it-works)
- [Which version should I use?](#which-version-should-i-use)
- [Windows](#windows)
  - [Option A: ready-made `.exe`](#windows-option-a-ready-made-exe)
  - [Option B: from source](#windows-option-b-from-source)
- [Ubuntu / Linux](#ubuntu--linux)
  - [Option A: ready-made executables](#ubuntu-option-a-ready-made-executables)
  - [Option B: from source](#ubuntu-option-b-from-source)
- [Your first download (web UI)](#your-first-download-web-ui)
- [Stopping the web UI](#stopping-the-web-ui)
- [Executables reference](#executables-reference)
- [Building and publishing the executables](#building-and-publishing-the-executables)
- [CLI usage](#interactive-cli-usage), [Web UI](#web-ui),
  [Configuration](#configuration), [Security](#security),
  [Troubleshooting](#troubleshooting)

## What it does

- Downloads a single video or an entire playlist from any site yt-dlp
  recognizes — run `yt-dlp --list-extractors` for the full list.
- Accepts the links apps actually give you to share: Facebook
  `share/` links, Instagram posts and reels, and TikTok links —
  including TikTok Lite (`lite.tiktok.com`), short links, and links
  carrying only a video id, which are rewritten into a form that
  downloads.
- Builds the quality menu from what the site *actually* offers (not a
  fixed YouTube-shaped list), so odd resolutions, audio-only sites, and
  single-format sites all work correctly.
- Lets you choose how files are named: original title, sequential
  numbers, or a custom pattern like `lesson_{number}`.
- Lets you choose the destination folder (creating it if needed).
- Downloads playlist items in parallel (configurable) for faster runs,
  with live per-item and overall progress.
- Downloads subtitles alongside the video/audio (pick from the
  languages the site actually reports, manual or auto-generated), or
  subtitles only, with no video/audio at all.
- Resumes interrupted downloads automatically (via yt-dlp).
- Remembers your preferences in `config.json` for next time.
- Skips, overwrites, or asks about files that already exist.
- Works the same way from an interactive menu, command-line flags, or
  a browser (`webmain.py`).

## How it works

```
 ┌──────────────── Media Downloader ────────────────┐
 │                                                  │
 │  CLI (main.py)          Web UI (webmain.py)      │
 │  menus + flags          local web server on      │
 │        │                127.0.0.1:8765, used     │
 │        │                from your browser        │
 │        └──────┬──────────────┘                   │
 │               ▼                                  │
 │     shared download engine (app/)                │
 │               │                                  │
 │       ┌───────┴────────┐                         │
 │       ▼                ▼                         │
 │    yt-dlp           FFmpeg                       │
 │  reads the site,   joins video + audio,          │
 │  downloads the     makes MP3s                    │
 │  streams                                         │
 └──────────────────────────────────────────────────┘
```

1. **You give it a link.** You paste it into the web page or type it
   in the CLI. It can be a single video or a playlist, from YouTube or
   any other site yt-dlp supports.
2. **It analyzes the link.** yt-dlp asks the site which qualities and
   subtitles really exist, and the app shows you only those.
3. **You choose.** Pick the quality, file names, destination folder and
   subtitles.
4. **It downloads.** Sites often send video and audio as separate
   streams. yt-dlp downloads them (several playlist items at once), and
   FFmpeg joins them into one `.mp4`. Progress updates live.
5. **The files are saved** in the folder you chose. An interrupted
   download resumes where it stopped.

**The web UI is not a website on the internet.** It's a small server
that runs **on your own computer** and only accepts connections from
your computer (`127.0.0.1`). Your browser is just the screen for it.
That's why the program has to keep running while you use the page.

**The ready-made executables** (`.exe` on Windows, no extension on
Ubuntu) contain Python, every library, and FFmpeg in one file. When
started, the program unpacks itself into a temporary folder, runs, and
removes that folder when it exits. That's why nothing needs to be
installed, and why the first start takes a few seconds.

## Which version should I use?

| | **Option A: ready-made executables** | **Option B: from source** |
|---|---|---|
| Install Python? | No | Yes |
| Install FFmpeg? | No, it's built in | Yes |
| Setup time | About 2 minutes | About 10 minutes |
| Download size | About 50 MB per program (Linux); ~57 MB on Windows | Small, plus Python and FFmpeg |
| Update yt-dlp yourself | No, download a newer release | Yes, one command |
| Best for | Just using the app | Changing the code, or always having the latest yt-dlp |

There are **two programs** in each option:

| Program | What it is | Windows | Ubuntu | From source |
|---|---|---|---|---|
| **Web UI** | Browser interface (easiest) | `media-downloader-ui.exe` | `media-downloader-ui` | `webmain.py` |
| **CLI** | Terminal menus and flags | `media-downloader-cli.exe` | `media-downloader-cli` | `main.py` |

The ready-made programs are published on the
**[Releases page](https://github.com/MoustafaMohamed-PK/Python-Videos-Playlist-Download/releases/latest)**,
not in the code itself. See
[Why the executables aren't in the repository](#why-the-executables-arent-in-the-repository).

---

## Windows

### Windows option A: ready-made `.exe`

**Requirements:** 64-bit Windows 10 or 11, and internet access. Nothing
else.

**1. Download**

1. Open the
   **[latest release](https://github.com/MoustafaMohamed-PK/Python-Videos-Playlist-Download/releases/latest)**.
2. Under **Assets**, click `media-downloader-ui.exe` (and
   `media-downloader-cli.exe` too, if you want the command-line
   version).
3. If your browser warns that the file "isn't commonly downloaded",
   choose **Keep** (in Edge: **⋯ → Keep → Keep anyway**).

**2. Put the files in their own folder**

Create a folder such as `C:\Users\<you>\MediaDownloader\` and move the
`.exe` files there. The app creates these next to the `.exe`:

```
MediaDownloader\
├── media-downloader-ui.exe
├── media-downloader-cli.exe
├── config.json        ← your saved settings (created automatically)
├── logs\              ← log files
└── downloads\         ← default download folder (web UI)
```

Avoid folders that need admin rights to write to, such as
`C:\Program Files`.

**3. Start the web UI**

1. Double-click `media-downloader-ui.exe`.
2. **The first time only**, Windows may show *"Windows protected your
   PC"*. Click **More info → Run anyway**. The file isn't code-signed,
   so this is normal.
3. A black **console window** opens and prints:
   ```
   Media Downloader web UI: http://127.0.0.1:8765
   Download root: C:\Users\<you>\MediaDownloader\downloads
   ```
4. A few seconds later, your browser opens **http://127.0.0.1:8765**.
   If it doesn't, open that address yourself.

**Keep the console window open while you use the page. It's the app
itself.** You can minimize it.

**4. Download something:** see
[Your first download](#your-first-download-web-ui).

**5. Stop the app when you're done.** Use any of these:

- click **Stop app** at the top right of the page
- close the console window
- press `Ctrl+C` in the console window
- run `.\media-downloader-ui.exe --stop` in PowerShell

**6. (Optional) Create a desktop shortcut**

Right-click `media-downloader-ui.exe` → **Show more options** → **Send
to** → **Desktop (create shortcut)**. The shortcut still keeps your
settings and downloads in the original folder.

**7. (Optional) Use the CLI**

Open the folder in File Explorer, click the address bar, type
`powershell`, and press Enter. Then run:

```powershell
.\media-downloader-cli.exe                   # interactive menu
.\media-downloader-cli.exe --url "https://www.youtube.com/watch?v=..." --quality 1080p --output .\downloads
.\media-downloader-cli.exe --url "https://www.youtube.com/playlist?list=..." --quality 720p --output .\downloads --name numbered
.\media-downloader-cli.exe --url "https://www.youtube.com/watch?v=..." --quality audio --output .\music
.\media-downloader-cli.exe --help            # all options
```

Double-clicking `media-downloader-cli.exe` also works; it opens the
interactive menu in a console window. All options are described in
[CLI (non-interactive) usage](#cli-non-interactive-usage).

**Updating:** stop the app, download the new `.exe` files from the
latest release, and replace the old ones. `config.json` and your
downloads stay where they are.

**Uninstalling:** stop the app and delete the folder. Nothing else is
installed anywhere.

**Problems?**

| Problem | Fix |
|---|---|
| "Windows protected your PC" | **More info → Run anyway** (first run only). |
| Antivirus deletes or blocks the `.exe` | Some antivirus tools flag self-extracting Python programs. Restore the file and add an exception for the folder. |
| Console opens and closes immediately | Open PowerShell in the folder and run `.\media-downloader-ui.exe` to see the error message. |
| Browser didn't open | Open **http://127.0.0.1:8765** yourself. |
| "Media Downloader is already running" | It's already open. Use the browser tab, or stop it with `--stop`. |
| Port 8765 is used by another program | `.\media-downloader-ui.exe --port 9000`, then open http://127.0.0.1:9000 |
| A site stopped working | Sites change often. Download the newest release, which includes a newer yt-dlp. |

### Windows option B: from source

**Requirements:** Python 3.9+ (3.12 recommended), FFmpeg, and Git
(optional). Run every command below in **PowerShell**.

**1. Install Python 3.12**

```powershell
winget install Python.Python.3.12
```

Or download it from <https://www.python.org/downloads/windows/>. In the
installer, **tick "Add python.exe to PATH"** before you click Install.

**2. Install FFmpeg**

```powershell
winget install Gyan.FFmpeg
```

Or download a build from <https://www.gyan.dev/ffmpeg/builds/>, extract
it, and add its `bin` folder to your PATH (*Start → "Edit the system
environment variables" → Environment Variables → Path → New*).

**3. Install Git** (skip this if you'll download the ZIP instead)

```powershell
winget install Git.Git
```

**4. Close PowerShell and open a new window** so it picks up the new
PATH, then check that everything is installed:

```powershell
python --version     # Python 3.12.x
ffmpeg -version      # prints FFmpeg version info
git --version
```

**5. Get the project**

```powershell
cd $HOME
git clone https://github.com/MoustafaMohamed-PK/Python-Videos-Playlist-Download.git
cd Python-Videos-Playlist-Download
```

Without Git: on the GitHub page, click **Code → Download ZIP**, extract
it, and `cd` into the extracted folder.

**6. Create and activate a virtual environment**

A virtual environment keeps this project's libraries separate from the
rest of your system.

```powershell
python -m venv venv
venv\Scripts\activate
```

Your prompt now starts with `(venv)`. If PowerShell says *"running
scripts is disabled on this system"*, run this once, then activate
again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**7. Install the Python libraries**

```powershell
pip install -r requirements.txt
```

**8. Run it**

```powershell
python webmain.py --open-browser    # web UI, opens http://127.0.0.1:8765
python main.py                      # or the CLI (interactive menu)
```

Then follow [Your first download](#your-first-download-web-ui). Stop
the web UI with **Stop app**, `Ctrl+C`, or `python webmain.py --stop`
from a second window.

**Next time**, you only need:

```powershell
cd $HOME\Python-Videos-Playlist-Download
venv\Scripts\activate
python webmain.py --open-browser
```

**Updating:**

```powershell
cd $HOME\Python-Videos-Playlist-Download
venv\Scripts\activate
git pull
pip install --upgrade -r requirements.txt   # also updates yt-dlp
```

**Problems?**

| Problem | Fix |
|---|---|
| `python` opens the Microsoft Store | Use `py` instead of `python`, or turn off *Settings → Apps → Advanced app settings → App execution aliases → python.exe*. |
| `'ffmpeg' is not recognized` | FFmpeg isn't on PATH. Redo step 2, then **open a new PowerShell window**. |
| `pip` not found | Use `python -m pip install -r requirements.txt`. |
| `ModuleNotFoundError: No module named 'flask'` | The venv isn't active. Run `venv\Scripts\activate` first. |
| Web UI page doesn't load | Keep the window running `webmain.py` open, and use exactly `http://127.0.0.1:8765`. |
| Port 8765 already in use | `python webmain.py --port 9000` |

---

## Ubuntu / Linux

### Ubuntu option A: ready-made executables

**Requirements:** 64-bit (x86-64) Ubuntu 22.04 or newer. Debian 12+,
Linux Mint 21+ and similar distros also work. You also need internet
access. Nothing else needs to be installed.

Check your system:

```bash
uname -m         # must print x86_64
ldd --version    # first line must show 2.35 or higher
```

**1. Download**

In a terminal:

```bash
mkdir -p ~/MediaDownloader && cd ~/MediaDownloader
wget https://github.com/MoustafaMohamed-PK/Python-Videos-Playlist-Download/releases/latest/download/media-downloader-ui
wget https://github.com/MoustafaMohamed-PK/Python-Videos-Playlist-Download/releases/latest/download/media-downloader-cli
```

Or download both files from the
**[latest release](https://github.com/MoustafaMohamed-PK/Python-Videos-Playlist-Download/releases/latest)**
page in your browser, then move them into `~/MediaDownloader`.

**2. Make them executable (once)**

Downloaded files aren't allowed to run until you give them permission:

```bash
cd ~/MediaDownloader
chmod +x media-downloader-ui media-downloader-cli
```

**3. Start the web UI**

```bash
cd ~/MediaDownloader
./media-downloader-ui
```

The terminal prints the address, and a few seconds later your browser
opens **http://127.0.0.1:8765**. **Keep the terminal open while you use
the page.** Settings, logs and downloads are created in
`~/MediaDownloader`:

```
~/MediaDownloader/
├── media-downloader-ui
├── media-downloader-cli
├── config.json        ← your saved settings
├── logs/
└── downloads/         ← default download folder (web UI)
```

> The `./` means "in this folder". Run the command from the folder
> that contains the file, or give its full path
> (`~/MediaDownloader/media-downloader-ui`). Otherwise you'll get
> `No such file or directory`.

**4. Download something:** see
[Your first download](#your-first-download-web-ui).

**5. Stop the app when you're done.** Use any of these:

- click **Stop app** at the top right of the page
- press `Ctrl+C` in the terminal
- close the terminal
- run `~/MediaDownloader/media-downloader-ui --stop` from any terminal

**6. (Optional) Run it in the background**

To start it without keeping a terminal open, and stop it later:

```bash
cd ~/MediaDownloader
nohup ./media-downloader-ui > ui.log 2>&1 &    # start in the background
./media-downloader-ui --stop                    # stop it later
```

Or save these as `start.sh` and `stop.sh` in `~/MediaDownloader`:

```bash
#!/usr/bin/env bash
# start.sh
cd "$(dirname "$0")" && nohup ./media-downloader-ui > ui.log 2>&1 &
```

```bash
#!/usr/bin/env bash
# stop.sh
cd "$(dirname "$0")" && ./media-downloader-ui --stop
```

Then run `chmod +x start.sh stop.sh` once, and use `./start.sh` and
`./stop.sh`.

**7. (Optional) Add it to the applications menu**

```bash
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/media-downloader.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Media Downloader
Comment=Download videos and playlists
Exec=$HOME/MediaDownloader/media-downloader-ui
Path=$HOME/MediaDownloader
Terminal=true
Icon=folder-download
Categories=Network;AudioVideo;
EOF
```

"Media Downloader" now appears in your applications list. It opens a
terminal window, and closing that window stops the app.

**8. (Optional) Use the CLI**

```bash
cd ~/MediaDownloader
./media-downloader-cli                       # interactive menu
./media-downloader-cli --url "https://www.youtube.com/watch?v=..." --quality 1080p --output ./downloads
./media-downloader-cli --url "https://www.youtube.com/playlist?list=..." --quality 720p --output ./downloads --name numbered
./media-downloader-cli --url "https://www.youtube.com/watch?v=..." --quality audio --output ./music
./media-downloader-cli --help                # all options
```

To run it from any folder as just `media-downloader-cli`, link it into
your personal `bin` folder:

```bash
mkdir -p ~/.local/bin
ln -sf ~/MediaDownloader/media-downloader-cli ~/.local/bin/media-downloader-cli
# open a new terminal, then: media-downloader-cli --help
```

**Updating:** stop the app, then download the files again as in
step 1 (`wget -O media-downloader-ui <url>` overwrites the old file)
and repeat step 2. Your settings and downloads are kept.

**Uninstalling:**

```bash
~/MediaDownloader/media-downloader-ui --stop
rm -rf ~/MediaDownloader
rm -f ~/.local/share/applications/media-downloader.desktop ~/.local/bin/media-downloader-cli
```

**Problems?**

| Problem | Fix |
|---|---|
| `No such file or directory` | You're not in the folder with the file. Run `cd ~/MediaDownloader` first, or use the full path. |
| `Permission denied` | Run `chmod +x media-downloader-ui media-downloader-cli`. |
| ``version `GLIBC_2.xx' not found`` | Your Linux is older than Ubuntu 22.04. Use [Option B](#ubuntu-option-b-from-source) instead. |
| `cannot execute binary file: Exec format error` | Your computer isn't x86-64 (e.g. a Raspberry Pi). Use [Option B](#ubuntu-option-b-from-source). |
| Browser didn't open | Open **http://127.0.0.1:8765** yourself. On a server with no screen, use `--no-browser`. |
| "Media Downloader is already running" | It's already open. Use the browser tab, or stop it with `--stop`. |
| Port 8765 is used by another program | `./media-downloader-ui --port 9000` |
| A site stopped working | Download the newest release, which includes a newer yt-dlp. |

### Ubuntu option B: from source

**Requirements:** Python 3.9+, FFmpeg, and Git. Ubuntu 22.04 and newer
already ship a suitable Python.

**1. Install the system packages**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```

Check:

```bash
python3 --version    # 3.9 or newer
ffmpeg -version      # prints FFmpeg version info
```

**2. Get the project**

```bash
cd ~
git clone https://github.com/MoustafaMohamed-PK/Python-Videos-Playlist-Download.git
cd Python-Videos-Playlist-Download
```

**3. Create and activate a virtual environment**

```bash
python3 -m venv venv
source venv/bin/activate
```

Your prompt now starts with `(venv)`.

**4. Install the Python libraries**

```bash
pip install -r requirements.txt
```

**5. Run it**

```bash
python webmain.py --open-browser    # web UI, opens http://127.0.0.1:8765
python main.py                      # or the CLI (interactive menu)
```

Then follow [Your first download](#your-first-download-web-ui). Stop
the web UI with **Stop app**, `Ctrl+C`, or `python webmain.py --stop`
from another terminal.

**Next time**, you only need:

```bash
cd ~/Python-Videos-Playlist-Download
source venv/bin/activate
python webmain.py --open-browser
```

**Updating:**

```bash
cd ~/Python-Videos-Playlist-Download
source venv/bin/activate
git pull
pip install --upgrade -r requirements.txt   # also updates yt-dlp
```

**Problems?**

| Problem | Fix |
|---|---|
| `The virtual environment was not created successfully` | `sudo apt install python3-venv` (or `python3.12-venv`), then repeat step 3. |
| `error: externally-managed-environment` | The venv isn't active. Run `source venv/bin/activate` first. |
| `ModuleNotFoundError: No module named 'flask'` | Same: activate the venv. |
| FFmpeg warning before downloads | `sudo apt install ffmpeg` |
| Port 8765 already in use | `python webmain.py --port 9000` |

---

## Your first download (web UI)

This works the same for the `.exe`, the Ubuntu executable, and
`webmain.py`.

1. **Paste a link** into **Video or playlist URL** and click
   **Analyze**. The app reads the video's title, thumbnail, length and
   site. For a playlist, it also shows the number of items.
2. **Choose the options:**
   - **Quality:** only the qualities this video really has.
     **Best available** picks the highest one, and **Audio only**
     saves an MP3.
   - **File naming:** *Original title* (`My Video.mp4`) or *Sequential
     numbering* (`1.mp4`, `2.mp4`, …), which is useful for courses and
     playlists.
   - **Subtitles:** tick the languages you want. Tick **Subtitles only
     (skip video/audio)** to download just the subtitle files.
   - **Destination folder:** type a path, or click **Browse…** to pick
     a folder (you can create a new one there).
   - **If a file already exists:** *Skip*, *Overwrite*, or *Ask me*.
   - **Playlist items in parallel:** how many playlist videos download
     at once (3 is a good default).
3. Click **Start download**. A card appears under **Jobs**, showing
   live progress, speed and time remaining. For a playlist, it shows
   each item too.
4. When it's done, the files are in your destination folder. You can
   also click each file in the job card to save it through the
   browser. Use **Cancel** to stop a job partway.
5. Reloading the page keeps your jobs, and the app remembers your
   choices for next time.

When you're finished, click **Stop app** (see
[Stopping the web UI](#stopping-the-web-ui)).

## Stopping the web UI

Any of these works, for the `.exe`, the Ubuntu executable, and
`python webmain.py` alike:

| How | Details |
|---|---|
| **Stop app** button | Top right of the page. It asks for confirmation, and warns you if downloads are still running. |
| `--stop` | Run the same program again with `--stop`. This works from any terminal, even when the app was started by double-clicking, from the menu, or in the background. |
| Close the console/terminal window | The window that opened when the app started. |
| `Ctrl+C` | In that window. |

```powershell
# Windows
.\media-downloader-ui.exe --stop
.\media-downloader-ui.exe --stop --port 9000     # if you started it with --port 9000
```

```bash
# Ubuntu
./media-downloader-ui --stop
./media-downloader-ui --stop --port 9000

# From source (either OS)
python webmain.py --stop
```

`--stop` waits until the app has really exited. It prints `Media
Downloader on port 8765 has stopped.` and returns exit code `0`. If the
app wasn't running, it prints `Media Downloader is not running on port
8765.` and returns `1`.

Downloads still in progress when you stop are cancelled. Their partial
files are kept, and the download resumes where it left off the next
time you download the same video.

A double-clickable `stop.bat` for Windows (put it next to the `.exe`):

```bat
@echo off
cd /d "%~dp0"
media-downloader-ui.exe --stop
pause
```

## Executables reference

### Web UI options

These are the same for `media-downloader-ui`, `media-downloader-ui.exe`
and `python webmain.py`:

| Option | Meaning |
|---|---|
| `--port 9000` | Use another port (default `8765`). |
| `--root <folder>` | Default download folder (default: `downloads` in the current folder). |
| `--config <file>` | Use another settings file (default: `config.json` in the current folder). |
| `--no-browser` | Don't open the browser (the executables open it by default). |
| `--open-browser` | Open the browser (`webmain.py` doesn't by default). |
| `--stop` | Stop the running app on `--port`. |
| `--host <addr>` | Listen on another address. Read [Security](#security) first. |

If you start the web UI while it's already running, it doesn't start a
second copy. It just opens the browser to the running one.

The CLI executable takes exactly the same options as `python main.py`.
See [CLI (non-interactive) usage](#cli-non-interactive-usage).

### Where files go

- `config.json` and `logs/` are created in the **folder the program is
  started from**. When you double-click, or use a shortcut or the menu
  entry above, that's the program's own folder.
- The web UI saves to `downloads/` in that same folder, unless you
  choose another folder in the page, pass `--root`, or set
  `web_download_root` in `config.json`.

### Things to expect

- **Startup pause:** the program unpacks itself into a temporary folder
  on every start — about a second on Linux, a little longer on Windows
  and on the very first run.
- **Unsigned file warnings:** Windows SmartScreen or your browser may
  warn about the `.exe` on first use. It isn't code-signed.
- **Antivirus:** some tools flag self-extracting Python programs. Add
  an exception if needed.
- **yt-dlp is frozen inside:** sites change often. If one stops
  working, download a newer release (or use the source version and
  `pip install --upgrade -r requirements.txt`).
- **Size:** measured on the v2.0.0 release — 48.6 MB and 50.0 MB on
  Linux, 56.5 MB and 57.8 MB on Windows, against 146-182 MB in v1.0.0.
  Python, all libraries and FFmpeg are inside, and FFmpeg alone is
  roughly two thirds of that.

## Building and publishing the executables

*This section is for maintainers. Users should download the files from
Releases.*

### Why the executables aren't in the repository

`.gitignore` excludes **only build output**: `build/`, `dist/`,
`.build-venv/` and `.build-wine/`. The scripts that *create* the
programs (`build.sh`, `build.ps1`, `packaging/`, `.github/`) **are**
committed.

The finished programs (`dist/windows/*.exe` and
`dist/linux/media-downloader-*`) are ignored because:

- **They're generated:** anyone can rebuild them with the scripts
  below.
- **They'd bloat the history:** at 49-58 MB each, committing them
  would add another ~210 MB (four files) to the repository on every
  rebuild.

They're published on **GitHub Releases** instead, which allows files up
to 2 GB.

### Automatic builds with GitHub Actions (recommended)

[`.github/workflows/release.yml`](.github/workflows/release.yml) builds
everything on GitHub's machines. You don't need Wine or a Windows PC.

**Full explanation:** [docs/github-actions-pipeline.md](docs/github-actions-pipeline.md)
covers triggers, each job and step, the workflow file line by line,
publishing, reading results, fixing failures, design decisions and
costs.

```
git tag v1.0.0 && git push origin v1.0.0
                    │
        ┌───────────┴─────────────┐
        ▼                         ▼
  Windows machine            Ubuntu 22.04 machine
  install Python 3.12        install Python 3.12
  run build.ps1              run the test suite
    → *-cli.exe              run ./build.sh linux
    → *-ui.exe                 → media-downloader-cli
                               → media-downloader-ui
        └───────────┬─────────────┘
                    ▼
     create GitHub Release "v1.0.0"
     and attach all 4 files
```

- **Publishing a release:** push a tag that starts with `v` (as
  above). About 10 minutes later, the files appear under **Releases →
  v1.0.0 → Assets**, and the download links in this README point at
  them.
- **Testing without publishing:** open **Actions → Build executables
  → Run workflow**. The files are attached to that run as artifacts.
- **Why each platform gets its own machine:** PyInstaller can't
  cross-compile, so Windows programs have to be built on Windows and
  Linux programs on Linux.
- **Why Ubuntu 22.04:** a Linux program only runs on systems at least
  as new as the one it was built on. Building on the oldest supported
  runner makes the files work on Ubuntu 22.04 and newer.
- **Tests:** if they fail, nothing is published.

To publish a new version later, bump the tag (`v1.0.1`, `v1.1.0`, …).

### Building locally

The build scripts create an isolated build environment, download a
static FFmpeg, and run PyInstaller with
`packaging/media-downloader.spec`.

**On Ubuntu:**

Requirements:

- A Python 3.10–3.13 **with a shared libpython**, plus `venv` or
  `virtualenv`. Ubuntu's own `python3.12` works:
  `sudo apt install python3.12 python3.12-venv`. The script picks a
  suitable interpreter automatically, and rejects a Python compiled
  without `--enable-shared`.
- `curl`, `tar`, `xz-utils`, `unzip`, about 2 GB of disk space, and
  internet access.
- For Windows files: Wine (`sudo apt install wine64`).

```bash
./build.sh linux      # -> dist/linux/media-downloader-cli, media-downloader-ui
./build.sh windows    # -> dist/windows/*.exe, cross-built through Wine
./build.sh            # both
```

The results are in `dist/linux/`, not the project root:

```bash
./dist/linux/media-downloader-ui
```

**On Windows:**

Requirements: Python 3.10–3.13 from python.org (with the `py` launcher),
PowerShell, and internet access.

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1   # -> dist\windows\
```

**Notes:**

- Downloaded FFmpeg binaries are cached in `build/`. Delete `build/`,
  `dist/`, `.build-venv/` and `.build-wine/` to start clean.
- Linux files downloaded from Actions or Releases lose their executable
  permission, so run `chmod +x` on them.
- The bundled FFmpeg (from
  [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)) is
  GPL-licensed. Keep that in mind if you redistribute the executables.

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
| `--subtitles`   | Comma-separated subtitle language codes to download, e.g. `en,es`.    |
| `--subtitles-only` | Skip video/audio entirely and download only the `--subtitles` languages. |
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
FFmpeg is used to mux them. H.264 video with AAC audio is preferred
over newer codecs — AV1, VP9 and H.265/HEVC — and merged into `.mp4`,
because many common players (Windows' built-in video app, older
VLC/QuickTime builds, TVs, phone galleries) can't decode those newer
ones: the file opens, the sound plays, and the picture stays black.

Two sites need this handling most:

- **Facebook** often has only AV1 in its separate video streams, while
  its H.264 copy sits in a combined stream the app falls back to.
- **TikTok** labels its codecs `h264`/`aac`, and its highest quality is
  usually H.265, so the app takes the H.264 copy instead.

The trade-off is deliberate: when the only higher resolution is in a
codec your player may not show, the app picks the slightly lower one
that plays everywhere. On webm/vp9/opus-only sites, it doesn't force an
incompatible mp4 remux — the container follows the codecs actually
available. Audio-only downloads are extracted to `.mp3` regardless of
source format.

## Subtitles

For a single video, the app reports the subtitle languages the site
actually has (manual, human-authored captions, and auto-generated
ones — a language only available as an auto-generated caption is
labeled accordingly, since the accuracy differs). For a playlist,
per-item subtitle tracks aren't known upfront, so you type language
codes directly (e.g. `en`, `es`) instead of picking from a list.

Choose one of three modes, in the interactive CLI or the web UI:

- **Video/audio** — no subtitles (the default).
- **Video/audio + subtitles** — the selected languages are saved as
  `.srt` sidecar files next to the video (e.g. `Title.en.srt`),
  converted from the site's native format (usually `.vtt`) when
  FFmpeg is available, left in that native format otherwise.
- **Subtitles only** — downloads just the subtitle files for the
  selected languages, skipping video/audio entirely.

In non-interactive mode, use `--subtitles en,es` (alongside a normal
video/audio download) or `--subtitles en,es --subtitles-only` (nothing
but the subtitles).

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
site. A post holding several videos (an Instagram carousel, say) counts
as one too: every entry reports the post's own URL, so the app selects
each video by its position in the post instead. The app shows the
playlist title and video count, then downloads every video — in parallel if `--concurrency`/the web UI's concurrency
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
- **Ask** — you're prompted for each conflicting file. In the CLI this
  blocks the terminal until you answer; in the web UI it pauses just
  that item, shows a prompt on its job card ("skip" or "overwrite"),
  and resumes once you click one. If a web prompt goes unanswered for
  10 minutes it defaults to skip rather than waiting forever. To avoid
  two conflicts racing for the same prompt, a playlist job using "ask"
  always downloads one item at a time regardless of the concurrency
  setting.

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
quality options, and pick where it goes: type a path directly, or
click **Browse…** to navigate the machine's folders (with a "new
folder" option) from a picker — the destination field starts pre-filled
with the configured download root but isn't limited to it. Check off
subtitle languages from the list (or type codes directly for a
playlist) and, optionally, "Subtitles only" to skip video/audio
entirely — see [Subtitles](#subtitles). Progress streams live (overall
and, for a playlist, each item), and finished files are downloaded
straight from the page. Reloading the page picks up any job still
running or already finished.

`--host`/`--port`/`--root`/`--config` mirror the CLI's `--config` and
let you change the bind address, port, and default download root.
To stop the server, click **Stop app** in the page, press `Ctrl+C`, or
run `python webmain.py --stop` (see
[Stopping the web UI](#stopping-the-web-ui)). See
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
`web_download_root` pre-fills the web UI's destination field and is
where a relative "subfolder" (the API's fallback when no explicit path
is given) resolves against — not a hard boundary the web UI enforces;
see **Security** below. Falls back to `download_folder`, then
`./downloads`, if unset.

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
- **The browser can read and write anywhere this OS user can.** By
  design, matching what the CLI already lets you type: the destination
  field accepts any path, and the folder browser (`/api/browse`) can
  navigate and create directories anywhere on the machine, not just
  under a configured root. There is no per-request confinement here —
  this is a deliberate tradeoff for a single-user, localhost-only tool
  that wants full filesystem access like a desktop app would, not a
  gap to be fixed. It relies entirely on the network-level protections
  below (binding to localhost, the Host check, the JSON-only check) to
  keep that access reachable only from this machine.
- **Files are served by job id + index, never by a client-supplied
  path.** The download endpoint looks up a completed job's own result
  by index; the path it serves was produced exclusively by this app's
  own `Downloader` while running that job (addressed only by an
  unguessable server-generated job id), never taken from a request
  parameter at serve time — so a client can retrieve a finished
  download regardless of which folder it landed in, without being able
  to name an arbitrary file to fetch.
- **CSRF / DNS rebinding**: every mutating request must declare
  `Content-Type: application/json` (a plain HTML form can't set that,
  and setting it from cross-origin JavaScript triggers a CORS
  preflight this server never answers, so the browser blocks the
  actual request), and the `Host` header must match the server's own
  bind address. Given the filesystem access above, these two checks
  are what actually stands between "only this machine can use it" and
  "any page open in this machine's browser can silently trigger
  downloads and directory listings" — treat them as load-bearing, not
  incidental.
- **This app is an arbitrary-URL fetcher by design** — that's the
  feature, not a bug to patch over with a domain allowlist (which
  would defeat the point of supporting "any site yt-dlp knows"). If you
  ever bind this somewhere other than `127.0.0.1`, understand that
  tradeoff explicitly — combined with unconfined filesystem access,
  binding beyond localhost means anyone who can reach the port can
  fetch arbitrary URLs and read/write arbitrary files this OS user can
  touch.
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
- **"The extractor is attempting impersonation, but none of these
  impersonate targets are available"** — some sites (Dailymotion among
  them) block non-browser HTTP clients and require yt-dlp to mimic a
  real browser's network fingerprint, which needs the `curl_cffi`
  package (already in `requirements.txt` — reinstall with
  `pip install -r requirements.txt`, or directly with
  `pip install curl_cffi`, if it's missing from your environment).
- **"This video is age-restricted and requires authentication"** — this
  app does not manage login cookies/authentication; age-restricted
  videos requiring sign-in can't be downloaded.
- **"The selected quality is not available"** — pick one of the
  qualities listed in the error message; the app won't silently
  substitute a different resolution. Note that a vertical video's
  heights are its long side: a 1080x1920 reel is listed as `1920p`.
- **"This TikTok post is unavailable"** — the post was deleted, is
  private, or isn't available in your region. TikTok also refuses some
  requests at random, which the app already retries a few times before
  reporting this.
- **The video plays as a black screen with sound** — the file is in a
  codec your player can't decode (AV1, VP9 or H.265). Downloads made
  with this version prefer H.264, so re-download the video; anything
  saved with an older version stays as it was.
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
├── requirements-build.txt   # PyInstaller (build-only)
├── build.sh                 # Build executables on Linux (+ Windows via Wine)
├── build.ps1                # Build Windows executables natively
├── packaging/
│   └── media-downloader.spec  # PyInstaller spec for both executables
├── .github/workflows/
│   └── release.yml          # CI: build on Windows + Ubuntu, publish a Release
├── docs/
│   └── github-actions-pipeline.md  # How the build/release pipeline works
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
