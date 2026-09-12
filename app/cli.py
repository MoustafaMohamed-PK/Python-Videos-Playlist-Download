"""
Command-line interface: menus, argument parsing, and orchestration.

This module ties together config, validators, formats, filename, and
downloader into the interactive and non-interactive (argument-driven)
workflows described in the project README.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from app.config import AppConfig, ConfigManager
from app.downloader import (
    Downloader,
    DownloadAppError,
    ExtractedTarget,
    ProgressEvent,
    VideoInfo,
    extract_target,
    fetch_formats_for_video,
)
from app.filename import FilenameError, validate_pattern
from app.formats import (
    QUALITY_LADDER,
    QualityChoice,
    describe_available_qualities,
    quality_is_available,
)
from app.utils import (
    ffmpeg_available,
    format_bytes,
    format_eta,
    format_speed,
    render_progress_bar,
    setup_logging,
)
from app.validators import (
    ValidationError,
    ensure_writable_directory,
    prompt_choice,
    prompt_int_in_range,
    prompt_yes_no,
    validate_destination_path,
    validate_youtube_url,
)

APP_TITLE = "YouTube Video Downloader"


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Download YouTube videos and playlists using yt-dlp.",
    )
    parser.add_argument("--url", help="YouTube video or playlist URL.")
    parser.add_argument(
        "--type", choices=["video", "playlist"], help="Whether the URL is a single video or a playlist."
    )
    parser.add_argument(
        "--quality",
        choices=[label for label, _ in QUALITY_LADDER],
        help="Desired quality (e.g. 1080p, 720p, best, audio).",
    )
    parser.add_argument("--output", help="Destination folder.")
    parser.add_argument(
        "--name",
        choices=["original", "numbered"],
        help="Filename mode: original title or sequential numbering.",
    )
    parser.add_argument(
        "--pattern",
        help="Custom filename pattern, e.g. 'lesson_{number}'. Implies pattern filename mode.",
    )
    parser.add_argument(
        "--format",
        dest="format_hint",
        help="(Reserved) explicit yt-dlp format override; advanced use only.",
    )
    parser.add_argument(
        "--overwrite",
        choices=["skip", "overwrite", "ask"],
        help="Behavior when the destination file already exists.",
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Force treating the URL as a playlist.",
    )
    parser.add_argument(
        "--config",
        help="Path to a config JSON file (default: ./config.json).",
    )
    return parser


# --------------------------------------------------------------------------
# Interactive prompts
# --------------------------------------------------------------------------

def print_header(title: str) -> None:
    line = "=" * 40
    print(f"\n{line}\n{title.center(40)}\n{line}")


def prompt_url() -> str:
    while True:
        raw = input("\nEnter YouTube URL: ").strip()
        try:
            return validate_youtube_url(raw)
        except ValidationError as exc:
            print(f"  {exc}")


def prompt_download_type() -> str:
    print("\nWhat do you want to download?")
    print("1. Single Video")
    print("2. Playlist")
    choice = prompt_int_in_range("Enter your choice: ", 1, 2)
    return "video" if choice == 1 else "playlist"


def prompt_quality(available_formats: Optional[list] = None) -> QualityChoice:
    print("\nAvailable qualities:")
    for i, (_, display) in enumerate(QUALITY_LADDER, start=1):
        print(f"{i}. {display}")
    choice = prompt_int_in_range("Choose quality: ", 1, len(QUALITY_LADDER))
    label = QUALITY_LADDER[choice - 1][0]
    return QualityChoice(label=label)


def prompt_filename_mode() -> tuple[str, Optional[str]]:
    print("\nHow should files be named?")
    print("1. Original YouTube title")
    print("2. Sequential numbering (1.mp4, 2.mp4, ...)")
    print("3. Custom pattern (e.g. lesson_{number})")
    choice = prompt_int_in_range("Choose naming: ", 1, 3)
    if choice == 1:
        return "original", None
    if choice == 2:
        return "numbered", None

    print("Supported placeholders: {number} {title} {playlist_index} {uploader}")
    while True:
        pattern = input("Enter filename pattern: ").strip()
        try:
            validate_pattern(pattern)
            return "pattern", pattern
        except FilenameError as exc:
            print(f"  {exc}")


def prompt_destination_folder(default: Optional[str] = None) -> Path:
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"Enter download folder{suffix}: ").strip()
        if not raw and default:
            raw = default
        try:
            path = validate_destination_path(raw)
        except ValidationError as exc:
            print(f"  {exc}")
            continue

        ok, err = ensure_writable_directory(path)
        if ok:
            return path
        if err == "does_not_exist":
            print("\nFolder does not exist.")
            print("Create it?")
            print("1. Yes")
            print("2. No")
            create_choice = prompt_int_in_range("Enter choice: ", 1, 2)
            if create_choice == 1:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    return path
                except OSError as exc:
                    print(f"  Could not create folder: {exc}")
            # else: loop and ask again
        else:
            print(f"  {err}")


def prompt_existing_file_behavior(default: str = "skip") -> str:
    print("\nIf a file already exists:")
    print("1. Skip existing files")
    print("2. Overwrite")
    print("3. Ask for each file")
    choice = prompt_int_in_range("Choose behavior: ", 1, 3)
    return {1: "skip", 2: "overwrite", 3: "ask"}[choice]


def interactive_ask_overwrite(path_str: str) -> str:
    print(f"\nFile already exists: {path_str}")
    return prompt_choice("Skip, overwrite, or ask again? [skip/overwrite]: ", ["skip", "overwrite"]).lower()


# --------------------------------------------------------------------------
# Progress / summary display
# --------------------------------------------------------------------------

def make_progress_printer():
    """Return a progress callback that prints compact, non-noisy updates.

    Uses carriage returns to update in place for downloading events, and
    a plain newline for completions, to avoid flooding the terminal.
    """
    last_pct_printed = {"value": -1}

    def callback(event: ProgressEvent) -> None:
        if event.status == "downloading":
            total = event.total_bytes
            downloaded = event.downloaded_bytes or 0
            fraction = (downloaded / total) if total else 0.0
            pct = int(fraction * 100)
            # Throttle to avoid noisy output: only print on >=1% change.
            if pct == last_pct_printed["value"]:
                return
            last_pct_printed["value"] = pct

            bar = render_progress_bar(fraction)
            playlist_prefix = (
                f"Video {event.video_index}/{event.video_total} | " if event.video_total > 1 else ""
            )
            line = (
                f"\r{playlist_prefix}{bar} {pct:3d}% | "
                f"{event.title[:40]:<40} | {event.quality_label:>6} | "
                f"{format_speed(event.speed):>10} | "
                f"{format_bytes(downloaded)}/{format_bytes(total)} | "
                f"ETA {format_eta(event.eta)}"
            )
            sys.stdout.write(line)
            sys.stdout.flush()
        elif event.status == "finished":
            last_pct_printed["value"] = -1
            sys.stdout.write("\n")
            sys.stdout.flush()

    return callback


def print_summary(run_result, target_kind: str, extra_title: Optional[str] = None) -> None:
    print_header("Download completed")
    if extra_title:
        print(f"Title      : {extra_title}")
    print(f"Downloaded : {run_result.downloaded}")
    print(f"Failed     : {run_result.failed}")
    print(f"Skipped    : {run_result.skipped}")
    print(f"\nLocation:\n{run_result.destination}")

    failed = [r for r in run_result.results if not r.success and not r.skipped]
    if failed:
        print("\nFailed videos:")
        for r in failed:
            print(f"  - {r.title} ({r.error})")


# --------------------------------------------------------------------------
# Core workflow (shared by interactive + CLI-argument modes)
# --------------------------------------------------------------------------

def run_download_workflow(
    url: str,
    quality_label: str,
    destination: Path,
    filename_mode: str,
    filename_pattern: Optional[str],
    existing_file_behavior: str,
    interactive: bool,
) -> int:
    """Runs the full extract -> confirm -> download -> summarize workflow.

    Returns a process exit code (0 = success, non-zero = error).
    """
    logger = setup_logging()

    try:
        target: ExtractedTarget = extract_target(url)
    except DownloadAppError as exc:
        print(f"\nERROR:\n{exc}")
        logger.error("Extraction failed for %s: %s", url, exc)
        return 1

    quality = QualityChoice(label=quality_label)

    # For a single video we already have real formats from extraction;
    # validate the requested quality against them so we never silently
    # substitute a different one.
    if not target.is_playlist:
        formats = target.formats or fetch_formats_for_video(url)
        if not quality_is_available(quality, formats):
            available = describe_available_qualities(formats)
            print("\nERROR:")
            print(f"The selected {quality_label} quality is not available for this video.")
            if available:
                print("\nAvailable:")
                for label in available:
                    display = dict(QUALITY_LADDER).get(label, label)
                    print(f"  {display}")
            return 1

    if not quality.is_audio_only and not ffmpeg_available():
        print(
            "\nNote: FFmpeg was not found on PATH. FFmpeg is required to merge "
            "separate video/audio streams. If the selected quality needs a "
            "merge, the download will fail. Please install FFmpeg and ensure "
            "it is on PATH."
        )

    video_count = len(target.videos)
    title_for_summary = target.playlist_title if target.is_playlist else target.videos[0].title

    print_header("Download Summary")
    print(f"Type       : {'Playlist' if target.is_playlist else 'Single Video'}")
    print(f"Title      : {title_for_summary}")
    if target.is_playlist:
        print(f"Videos     : {video_count}")
    print(f"Quality    : {quality_label}")
    naming_display = filename_pattern if filename_mode == "pattern" else filename_mode
    print(f"Naming     : {naming_display}")
    print(f"Output     : {destination}")

    if interactive:
        proceed = prompt_yes_no("\nStart download?", default=True)
        if not proceed:
            print("Cancelled.")
            return 0

    downloader = Downloader(
        destination=destination,
        quality=quality,
        filename_mode=filename_mode,
        filename_pattern=filename_pattern,
        existing_file_behavior=existing_file_behavior,
        progress_callback=make_progress_printer(),
        ask_overwrite_callback=interactive_ask_overwrite if interactive else None,
    )

    video_urls = _video_urls_for_target(url, target)
    metadatas = [
        {"title": v.title, "uploader": v.uploader} for v in target.videos
    ]

    run_result = downloader.download_many(video_urls, metadatas)
    print_summary(run_result, "playlist" if target.is_playlist else "video", title_for_summary)

    return 0 if run_result.failed == 0 else 2


def _video_urls_for_target(original_url: str, target: ExtractedTarget) -> List[str]:
    """Compute the per-video URL list for downloading.

    For a single video, that's just the original URL. For a playlist,
    yt-dlp's flat extraction gives each entry a "url" (often just the
    video id) -- normalize to a full watch URL.
    """
    if not target.is_playlist:
        return [original_url]

    urls = []
    for video in target.videos:
        entry_url = video.raw.get("url") or video.id
        if entry_url and entry_url.startswith("http"):
            urls.append(entry_url)
        else:
            urls.append(f"https://www.youtube.com/watch?v={video.id}")
    return urls


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def run_interactive(config: AppConfig, config_manager: ConfigManager) -> int:
    print_header(APP_TITLE)

    prompt_download_type()  # informational; extraction auto-detects playlist vs video
    url = prompt_url()
    quality = prompt_quality()
    filename_mode, filename_pattern = prompt_filename_mode()
    destination = prompt_destination_folder(default=config.download_folder or None)
    existing_behavior = prompt_existing_file_behavior(default=config.existing_file_behavior)

    # Persist choices as new defaults for next run.
    config.download_folder = str(destination)
    config.quality = quality.label
    config.filename_mode = filename_mode
    config.filename_pattern = filename_pattern or config.filename_pattern
    config.existing_file_behavior = existing_behavior
    config_manager.save(config)

    return run_download_workflow(
        url=url,
        quality_label=quality.label,
        destination=destination,
        filename_mode=filename_mode,
        filename_pattern=filename_pattern,
        existing_file_behavior=existing_behavior,
        interactive=True,
    )


def run_from_args(args: argparse.Namespace, config: AppConfig) -> int:
    if not args.url:
        print("ERROR: --url is required in non-interactive mode.")
        return 1

    try:
        url = validate_youtube_url(args.url)
    except ValidationError as exc:
        print(f"ERROR: {exc}")
        return 1

    quality_label = args.quality or config.quality

    if args.pattern:
        try:
            validate_pattern(args.pattern)
        except FilenameError as exc:
            print(f"ERROR: {exc}")
            return 1
        filename_mode = "pattern"
        filename_pattern = args.pattern
    else:
        filename_mode = args.name or config.filename_mode
        filename_pattern = config.filename_pattern if filename_mode == "pattern" else None

    output_str = args.output or config.download_folder
    if not output_str:
        print("ERROR: --output is required (no default download folder configured).")
        return 1

    try:
        destination = validate_destination_path(output_str)
    except ValidationError as exc:
        print(f"ERROR: {exc}")
        return 1

    ok, err = ensure_writable_directory(destination)
    if not ok:
        if err == "does_not_exist":
            try:
                destination.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(f"ERROR: Could not create destination folder: {exc}")
                return 1
        else:
            print(f"ERROR: {err}")
            return 1

    existing_behavior = args.overwrite or config.existing_file_behavior

    return run_download_workflow(
        url=url,
        quality_label=quality_label,
        destination=destination,
        filename_mode=filename_mode,
        filename_pattern=filename_pattern,
        existing_file_behavior=existing_behavior,
        interactive=False,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config_manager = ConfigManager(args.config) if args.config else ConfigManager()
    config = config_manager.load()

    try:
        if args.url:
            return run_from_args(args, config)
        return run_interactive(config, config_manager)
    except KeyboardInterrupt:
        print("\n\nDownload interrupted.")
        print("You can run the program again to resume the download.")
        return 130
    except DownloadAppError as exc:
        print(f"\nERROR:\n{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
