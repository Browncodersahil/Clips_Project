#!/usr/bin/env python3
"""
delete.py - Clean up all generated video clips, intermediate audio,
transcripts, highlights, jobs, and temporary data.

Usage:
    python delete.py          # Asks for confirmation before deleting
    python delete.py --yes    # Deletes all data immediately without prompting
    python delete.py -y       # Short alias for --yes
    python delete.py --keep-final  # Clean intermediate files but preserve Final_Clip/
"""

import sys
import os
import shutil
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.config import settings
except ImportError:
    settings = None


def format_bytes(num_bytes: int) -> str:
    """Formats bytes into human readable string (KB, MB, GB)."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024.0 or unit == "TB":
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} B"


def get_target_directories(keep_final: bool = False):
    """Returns dictionary of folder label -> Path to clean."""
    if settings:
        dirs = {
            "Downloads": settings.downloads_dir,
            "Full Audio": settings.audio_dir,
            "Audio Chunks": settings.chunks_dir,
            "Transcripts": settings.transcripts_dir,
            "Highlights": settings.highlights_dir,
            "Intermediate Clips": settings.clips_dir,
            "Job Logs & State": settings.jobs_dir,
        }
        if not keep_final:
            dirs["Final Clips (mp4 & json)"] = settings.final_clip_dir
    else:
        base = PROJECT_ROOT / "data"
        dirs = {
            "Downloads": base / "downloads",
            "Full Audio": base / "audio",
            "Audio Chunks": base / "chunks",
            "Transcripts": base / "transcripts",
            "Highlights": base / "highlights",
            "Intermediate Clips": base / "clips",
            "Job Logs & State": base / "jobs",
        }
        if not keep_final:
            dirs["Final Clips (mp4 & json)"] = base / "Final_Clip"
    return dirs


def clean_all(keep_final: bool = False, verbose: bool = True) -> int:
    """
    Deletes all files inside data directories and resets the folder structure.
    Returns total bytes freed.
    """
    target_dirs = get_target_directories(keep_final=keep_final)
    total_files_deleted = 0
    total_bytes_freed = 0

    print("\n" + "=" * 60)
    print(" 🧹 KICK STREAM CLIPPER - DATA CLEANUP")
    print("=" * 60)

    for label, folder in target_dirs.items():
        if not folder.exists():
            continue

        folder_files = 0
        folder_bytes = 0

        for item in folder.iterdir():
            # Don't delete .gitkeep if present
            if item.name == ".gitkeep":
                continue

            try:
                if item.is_file() or item.is_symlink():
                    size = item.stat().st_size
                    item.unlink()
                    folder_files += 1
                    folder_bytes += size
                elif item.is_dir():
                    size = sum(f.stat().st_size for f in item.glob("**/*") if f.is_file())
                    shutil.rmtree(item)
                    folder_files += 1
                    folder_bytes += size
            except Exception as e:
                print(f"  [!] Failed to remove {item}: {e}")

        total_files_deleted += folder_files
        total_bytes_freed += folder_bytes

        if verbose:
            print(f"  • {label:28} : {folder_files:3d} files removed ({format_bytes(folder_bytes)})")

    # Clean run.log if present
    log_file = (settings.log_file if settings else PROJECT_ROOT / "data" / "run.log")
    if log_file.exists():
        try:
            log_size = log_file.stat().st_size
            log_file.unlink()
            total_files_deleted += 1
            total_bytes_freed += log_size
            if verbose:
                print(f"  • {'Run Log':28} :   1 file removed ({format_bytes(log_size)})")
        except Exception as e:
            print(f"  [!] Failed to remove log file {log_file}: {e}")

    # Re-create all standard folders so pipeline runs cleanly without missing dir errors
    if settings:
        settings.ensure_directories()
    else:
        for folder in target_dirs.values():
            folder.mkdir(parents=True, exist_ok=True)

    print("-" * 60)
    print(f" Total files removed: {total_files_deleted}")
    print(f" Total disk space freed: {format_bytes(total_bytes_freed)}")
    print(" Folder structure has been reset and is ready for fresh runs.")
    print("=" * 60 + "\n")

    return total_bytes_freed


def main():
    parser = argparse.ArgumentParser(
        description="Delete all clips, intermediate audio/transcripts/highlights, and downloads."
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt and delete immediately."
    )
    parser.add_argument(
        "--keep-final",
        action="store_true",
        help="Keep completed reels in data/Final_Clip/ and only clean intermediate files."
    )

    args = parser.parse_args()

    # If --yes is not given and running interactively, confirm with user
    if not args.yes:
        target_dirs = get_target_directories(keep_final=args.keep_final)
        total_count = sum(
            len([f for f in folder.iterdir() if f.name != ".gitkeep"])
            for folder in target_dirs.values()
            if folder.exists()
        )

        if total_count == 0:
            print("\nAll data folders are already empty. Nothing to clean.")
            return

        mode_str = "intermediate files only" if args.keep_final else "ALL clips, downloads, and data"
        print(f"\nFound {total_count} files across data directories.")
        try:
            confirm = input(f"Are you sure you want to delete {mode_str}? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

        if confirm not in ["y", "yes"]:
            print("Cleanup cancelled.")
            sys.exit(0)

    clean_all(keep_final=args.keep_final)


if __name__ == "__main__":
    main()
