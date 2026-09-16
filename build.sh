#!/usr/bin/env bash
# Build standalone executables with PyInstaller.
#
#   ./build.sh          # build both Linux and Windows executables
#   ./build.sh linux     # build only dist/linux/media-downloader-{cli,ui}
#   ./build.sh windows   # build only dist/windows/media-downloader-{cli,ui}.exe
#                          via Wine (no Windows machine required)
#
# Windows executables are cross-built from Ubuntu by running a real
# Windows Python interpreter under Wine -- PyInstaller can't
# cross-compile, so this is the only way to produce a .exe without a
# Windows machine. If Wine isn't available/working, use build.ps1 on
# an actual Windows machine instead.
#
# FFmpeg is bundled into each executable (see packaging/media-downloader.spec
# and app/utils.py:use_bundled_ffmpeg) so the resulting binaries need
# nothing pre-installed on the target machine except libc.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TARGET="${1:-all}"
FFMPEG_RELEASE_BASE="https://github.com/BtbN/FFmpeg-Builds/releases/latest/download"

log() { echo "==> $*"; }

# PyInstaller needs a Python built with a shared libpython (`python3
# --enable-shared`); a statically-linked interpreter (common for
# from-source builds) fails at Analysis time with "Python was built
# without a shared library". Distro packages are normally built
# shared, so prefer those over whatever `python3` happens to resolve
# to first.
find_build_python() {
    local candidates=(python3.13 python3.12 python3.11 python3.10 python3)
    # An explicit BUILD_PYTHON (used by CI) wins over the search.
    if [ -n "${BUILD_PYTHON:-}" ]; then
        candidates=("$BUILD_PYTHON")
    fi
    local candidate
    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c "import sysconfig,sys; sys.exit(0 if sysconfig.get_config_var('Py_ENABLE_SHARED') else 1)" 2>/dev/null; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

build_linux() {
    log "Building Linux executables"

    if [ ! -d .build-venv ]; then
        local build_python
        if ! build_python="$(find_build_python)"; then
            cat <<'EOF' >&2
No Python interpreter with a shared libpython (required by PyInstaller)
was found. Install one, e.g.:

    sudo apt install python3.12 python3.12-venv

Then re-run: ./build.sh linux
EOF
            exit 1
        fi
        log "Using $build_python for the build venv"
        # `-m venv` needs the distro's <pyversion>-venv package (it
        # ships ensurepip separately on Debian/Ubuntu); fall back to
        # the `virtualenv` tool, which doesn't have that dependency,
        # if it's missing.
        local venv_err
        venv_err="$(mktemp)"
        if ! "$build_python" -m venv .build-venv 2>"$venv_err"; then
            if command -v virtualenv >/dev/null 2>&1; then
                log "'venv' module unavailable, falling back to 'virtualenv'"
                rm -rf .build-venv
                virtualenv --quiet -p "$build_python" .build-venv
            else
                cat "$venv_err" >&2
                echo "Install the venv package for $build_python (e.g. sudo apt install python3.12-venv)" >&2
                echo "or: sudo apt install python3-virtualenv" >&2
                rm -f "$venv_err"
                exit 1
            fi
        fi
        rm -f "$venv_err"
    fi
    .build-venv/bin/pip install --quiet --upgrade pip
    .build-venv/bin/pip install --quiet -r requirements.txt -r requirements-build.txt

    if [ ! -x build/ffmpeg/ffmpeg ]; then
        log "Downloading static FFmpeg (Linux)"
        mkdir -p build/ffmpeg
        local tmp_tar
        tmp_tar="$(mktemp)"
        curl -fL "${FFMPEG_RELEASE_BASE}/ffmpeg-master-latest-linux64-gpl.tar.xz" -o "$tmp_tar"
        local extracted_dir
        # pipefail must be off for this line: `head -1` closing the
        # pipe early sends tar a SIGPIPE (exit 141), which pipefail
        # would otherwise treat as this command failing outright.
        set +o pipefail
        extracted_dir="$(tar -tJf "$tmp_tar" | head -1 | cut -d/ -f1)"
        set -o pipefail
        tar -xJf "$tmp_tar" -C /tmp "${extracted_dir}/bin/ffmpeg" "${extracted_dir}/bin/ffprobe"
        cp "/tmp/${extracted_dir}/bin/ffmpeg" build/ffmpeg/ffmpeg
        cp "/tmp/${extracted_dir}/bin/ffprobe" build/ffmpeg/ffprobe
        chmod +x build/ffmpeg/ffmpeg build/ffmpeg/ffprobe
        rm -rf "$tmp_tar" "/tmp/${extracted_dir}"
    fi

    .build-venv/bin/pyinstaller --clean --noconfirm \
        --distpath dist/linux --workpath build/pyinstaller-linux \
        packaging/media-downloader.spec

    log "Smoke test"
    dist/linux/media-downloader-cli --help >/dev/null
    log "Linux build OK: dist/linux/media-downloader-cli, dist/linux/media-downloader-ui"
}

build_windows() {
    log "Building Windows executables (via Wine)"

    local wine_bin=""
    if command -v wine64 >/dev/null 2>&1; then
        wine_bin="$(command -v wine64)"
    elif command -v wine >/dev/null 2>&1; then
        wine_bin="$(command -v wine)"
    else
        cat <<'EOF'
Wine is required to build the Windows executables from Ubuntu. Install it with:

    sudo apt update && sudo apt install wine64

Then re-run: ./build.sh windows

(Alternatively, build natively on a Windows machine with build.ps1.)
EOF
        exit 1
    fi

    export WINEPREFIX="$ROOT_DIR/.build-wine"
    export WINEARCH=win64
    export WINEDEBUG=-all

    local python_version="3.12.7"
    local python_installer="python-${python_version}-amd64.exe"
    mkdir -p build
    if [ ! -f "build/${python_installer}" ]; then
        log "Downloading Windows Python ${python_version}"
        curl -fL "https://www.python.org/ftp/python/${python_version}/${python_installer}" \
            -o "build/${python_installer}"
    fi

    local wine_py="$WINEPREFIX/drive_c/Program Files/Python312/python.exe"
    if [ ! -f "$wine_py" ]; then
        log "Installing Python into the Wine prefix ($WINEPREFIX)"
        "$wine_bin" "build/${python_installer}" \
            /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 SimpleInstall=1
        # The installer finishes asynchronously under Wine.
        sleep 5
        if [ ! -f "$wine_py" ]; then
            echo "Windows Python install did not produce $wine_py -- check $WINEPREFIX manually." >&2
            exit 1
        fi
    fi

    "$wine_bin" "$wine_py" -m pip install --quiet --upgrade pip
    "$wine_bin" "$wine_py" -m pip install --quiet -r requirements.txt -r requirements-build.txt

    if [ ! -f build/ffmpeg-win/ffmpeg.exe ]; then
        log "Downloading static FFmpeg (Windows)"
        mkdir -p build/ffmpeg-win
        local tmp_zip unzip_dir extracted_dir
        tmp_zip="$(mktemp --suffix=.zip)"
        curl -fL "${FFMPEG_RELEASE_BASE}/ffmpeg-master-latest-win64-gpl.zip" -o "$tmp_zip"
        unzip_dir="$(mktemp -d)"
        unzip -q "$tmp_zip" -d "$unzip_dir"
        extracted_dir="$(find "$unzip_dir" -maxdepth 1 -mindepth 1 -type d | head -1)"
        cp "$extracted_dir/bin/ffmpeg.exe" build/ffmpeg-win/ffmpeg.exe
        cp "$extracted_dir/bin/ffprobe.exe" build/ffmpeg-win/ffprobe.exe
        rm -rf "$tmp_zip" "$unzip_dir"
    fi

    "$wine_bin" "$wine_py" -m PyInstaller --clean --noconfirm \
        --distpath dist/windows --workpath build/pyinstaller-windows \
        packaging/media-downloader.spec

    log "Smoke test"
    "$wine_bin" dist/windows/media-downloader-cli.exe --help >/dev/null
    log "Windows build OK: dist/windows/media-downloader-cli.exe, dist/windows/media-downloader-ui.exe"
}

case "$TARGET" in
    linux) build_linux ;;
    windows) build_windows ;;
    all)
        build_linux
        build_windows
        ;;
    *)
        echo "Usage: $0 [linux|windows|all]" >&2
        exit 1
        ;;
esac
