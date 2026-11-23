import os
import sys
from pathlib import Path

# Auto-switch to project virtual environment if run via system python3
PROJECT_ROOT = Path(__file__).resolve().parent
_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and sys.prefix != str(PROJECT_ROOT / ".venv"):
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

import argparse
import logging
from tqdm import tqdm
from app.config import settings
from app.schemas import JobStage
from app.pipeline.runner import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("kick_clipper_cli")

def main():
    parser = argparse.ArgumentParser(
        description="Kick Stream Auto-Clipper CLI: Generate ready-to-upload viral reels from Kick streams."
    )
    parser.add_argument("url", type=str, help="Kick stream/VOD URL or path to local test video")
    parser.add_argument("--max-clips", type=int, default=settings.MAX_CLIPS, help="Max clips to generate (0 = maximum / unlimited clips, default: 0)")
    parser.add_argument("--min-score", type=int, default=settings.MIN_SCORE, help="Minimum viral score 1-10 (default: 7)")
    parser.add_argument("--layout", type=str, choices=["blur", "crop"], default=settings.LAYOUT, help="Video layout ('blur' or 'crop')")
    parser.add_argument("--force", action="store_true", help="Force re-processing of intermediate steps")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary audio chunk files")
    parser.add_argument("--brief", type=str, default=None, help="Custom path to creator brief markdown file (default: briefs/brief.md)")
    parser.add_argument("--logo", type=str, default=None, help="Custom path to creator logo image (default: briefs/logo.png)")

    args = parser.parse_args()

    # Detect brief & logo
    detected_brief = settings.get_creator_brief(args.brief)
    detected_logo = settings.get_creator_logo_path(args.logo)

    max_clips_display = "Maximum / Unlimited" if (args.max_clips == 0 or args.max_clips is None) else str(args.max_clips)
    print("\n" + "="*60)
    print(" 🎬 KICK STREAM AUTO-CLIPPER")
    print(f" URL:         {args.url}")
    print(f" Max Clips:   {max_clips_display} | Min Score: {args.min_score} | Layout: {args.layout}")
    print(f" Creator Brief: {'Active (' + (args.brief or 'briefs/brief.md') + ')' if detected_brief else 'None (standard clip selection)'}")
    print(f" Creator Logo : {detected_logo.name + ' (bottom)' if detected_logo else 'None (no logo watermark)'}")
    print(f" Captions     : Small styled subtitles (size {settings.CAPTIONS_FONT_SIZE})")
    print("="*60 + "\n")

    pbar = tqdm(total=100, desc="Starting pipeline...", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}% [{elapsed}]")
    last_pct = [0]

    def on_progress(stage: JobStage, pct: int):
        diff = pct - last_pct[0]
        if diff > 0:
            pbar.update(diff)
            last_pct[0] = pct
        pbar.set_description(f"Stage: {stage.value}")

    try:
        result = run_pipeline(
            kick_url=args.url,
            max_clips=args.max_clips,
            min_score=args.min_score,
            layout=args.layout,
            force=args.force,
            keep_temp=args.keep_temp,
            brief_path=args.brief,
            logo_path=args.logo,
            progress_callback=on_progress
        )
        pbar.close()

        print("\n" + "="*60)
        print(" 🎉 PIPELINE FINISHED SUCCESSFULLY!")
        print(f" Output Folder: {settings.final_clip_dir.resolve()}")
        print(f" Total Completed Clips: {len(result['clips'])}")
        print("="*60)

        for name in result["clips"]:
            mp4_file = settings.final_clip_dir / f"{name}.mp4"
            json_file = settings.final_clip_dir / f"{name}.json"
            print(f"  • Reel: {mp4_file.name}")
            print(f"    Meta: {json_file.name}")

        if result.get("failed_clips"):
            print("\n⚠️ Failed clips:")
            for fc in result["failed_clips"]:
                print(f"  • {fc}")

    except Exception as e:
        pbar.close()
        print(f"\n❌ Error running clipper pipeline: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
