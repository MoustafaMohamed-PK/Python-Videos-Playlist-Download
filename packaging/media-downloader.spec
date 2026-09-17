# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the two standalone executables:

    media-downloader-cli   <- main.py    (the CLI)
    media-downloader-ui    <- webmain.py (the web UI)

Built via build.sh (Linux, and Windows through Wine) or build.ps1
(Windows, native). Both executables bundle FFmpeg (see
app.utils.use_bundled_ffmpeg) so nothing else needs to be installed on
the target machine.

Not meant to be invoked directly with plain `python`; run it through
`pyinstaller packaging/media-downloader.spec` (the build scripts do
this for you, with the right --distpath/--workpath per platform).
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# SPECPATH is injected by PyInstaller into this file's global namespace
# and points at the directory containing this spec (packaging/).
ROOT = Path(SPECPATH).resolve().parent  # noqa: F821

IS_WINDOWS = sys.platform.startswith("win")

# Static FFmpeg builds are downloaded by the build scripts into these
# folders before PyInstaller runs -- see build.sh / build.ps1.
FFMPEG_DIR = ROOT / "build" / ("ffmpeg-win" if IS_WINDOWS else "ffmpeg")
FFMPEG_EXT = ".exe" if IS_WINDOWS else ""

# Only ffmpeg is bundled, not ffprobe: the two binaries are static
# builds of nearly identical size (~80 MB each), and shipping both
# doubled every executable for no benefit. yt-dlp falls back to
# "ffmpeg -i" wherever it would otherwise probe (merging, audio
# extraction, remuxing, subtitle conversion all work unchanged); the
# only ffprobe-only path is an HLS-in-mp4 fixup, which degrades to a
# warning and still applies its fix.
ffmpeg_binaries = [
    (str(FFMPEG_DIR / f"ffmpeg{FFMPEG_EXT}"), "ffmpeg"),
]

# Stdlib/3rd-party packages nothing in this app imports. PyInstaller
# pulls some in through optional-import chains, where they are dead
# weight in a download tool: a GUI toolkit, the test suites, and the
# packaging machinery that only matters at build time.
EXCLUDED_MODULES = [
    "tkinter",
    "test",
    "unittest",
    "pydoc_data",
    "lib2to3",
    "setuptools",
    "pip",
    "wheel",
    "PyInstaller",
]

# curl_cffi ships a native extension plus data files (its bundled CA
# bundle, browser fingerprint profiles); collect_all grabs all of it.
curl_cffi_datas, curl_cffi_binaries, curl_cffi_hidden = collect_all("curl_cffi")

common_kwargs = dict(
    pathex=[str(ROOT)],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    cipher=block_cipher,
)

# --------------------------------------------------------------- CLI ----

cli_analysis = Analysis(
    [str(ROOT / "main.py")],
    binaries=ffmpeg_binaries + curl_cffi_binaries,
    datas=curl_cffi_datas,
    hiddenimports=curl_cffi_hidden,
    **common_kwargs,
)
cli_pyz = PYZ(cli_analysis.pure, cli_analysis.zipped_data, cipher=block_cipher)
cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    cli_analysis.binaries,
    cli_analysis.zipfiles,
    cli_analysis.datas,
    [],
    name="media-downloader-cli",
    console=True,
    upx=False,
)

# ---------------------------------------------------------------- UI ----

ui_datas = curl_cffi_datas + [
    (str(ROOT / "web" / "templates"), "web/templates"),
    (str(ROOT / "web" / "static"), "web/static"),
]

ui_analysis = Analysis(
    [str(ROOT / "webmain.py")],
    binaries=ffmpeg_binaries + curl_cffi_binaries,
    datas=ui_datas,
    hiddenimports=curl_cffi_hidden + ["waitress"],
    **common_kwargs,
)
ui_pyz = PYZ(ui_analysis.pure, ui_analysis.zipped_data, cipher=block_cipher)
ui_exe = EXE(
    ui_pyz,
    ui_analysis.scripts,
    ui_analysis.binaries,
    ui_analysis.zipfiles,
    ui_analysis.datas,
    [],
    name="media-downloader-ui",
    console=True,
    upx=False,
)
