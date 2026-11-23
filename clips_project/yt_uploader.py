import os
import sys
from pathlib import Path

# Auto-switch to project virtual environment if run via system python3
PROJECT_ROOT = Path(__file__).resolve().parent
_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and sys.prefix != str(PROJECT_ROOT / ".venv"):
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("yt_uploader")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = PROJECT_ROOT / "client_secrets.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"
TRACKER_FILE = settings.base_data_dir / "uploaded_youtube.json"

# US Peak Time Slots in EST (hours and minutes)
# Converted to UTC (EST is UTC-5)
US_PEAK_SLOTS_EST = [
    (11, 30),  # 11:30 AM EST
    (14, 0),   # 02:00 PM EST
    (16, 30),  # 04:30 PM EST
    (18, 30),  # 06:30 PM EST
    (20, 30),  # 08:30 PM EST
    (22, 0),   # 10:00 PM EST
    (23, 30),  # 11:30 PM EST
]


def load_tracker() -> Dict[str, Any]:
    """Loads records of previously uploaded clips."""
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_tracker(tracker: Dict[str, Any]):
    """Saves records of uploaded clips."""
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)


def get_authenticated_service():
    """Authenticates using client_secrets.json or cached token.json."""
    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            logger.warning(f"Could not load cached token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired YouTube OAuth token...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_FILE.exists():
                print("\n" + "!" * 65)
                print(" ERROR: 'client_secrets.json' was not found in the project root!")
                print("!" * 65)
                print("To upload via official YouTube Data API:")
                print(" 1. Go to https://console.cloud.google.com")
                print(" 2. Create a project and enable 'YouTube Data API v3'.")
                print(" 3. Go to Credentials -> Create Credentials -> OAuth Client ID (Desktop App).")
                print(" 4. Download JSON and save it as 'client_secrets.json' in this folder:")
                print(f"    {CLIENT_SECRETS_FILE.resolve()}")
                print("!" * 65 + "\n")
                sys.exit(1)

            logger.info("Starting Google OAuth2 browser consent flow...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for future runs
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
        logger.info(f"Saved authenticated session to {TOKEN_FILE.name}")

    return build("youtube", "v3", credentials=creds)


def generate_schedule_timestamps(total_clips: int, days: int = 7) -> List[datetime]:
    """
    Generates UTC timestamps for scheduling clips across N days
    starting from tomorrow, aligned with US Peak Hours (EST).
    """
    # Start scheduling from tomorrow to give today's channel room
    now_utc = datetime.now(timezone.utc)
    start_date = (now_utc + timedelta(days=1)).date()

    slots: List[datetime] = []
    # Calculate how many slots per day we need
    slots_per_day = max(1, (total_clips + days - 1) // days)

    current_day = 0
    slot_idx = 0

    for i in range(total_clips):
        day_offset = current_day % days
        target_date = start_date + timedelta(days=day_offset)

        # Choose EST slot time
        est_hour, est_minute = US_PEAK_SLOTS_EST[slot_idx % len(US_PEAK_SLOTS_EST)]
        
        # Convert EST (UTC-5) to UTC (+5 hours)
        est_tz = timezone(timedelta(hours=-5))
        sched_est = datetime(target_date.year, target_date.month, target_date.day, est_hour, est_minute, tzinfo=est_tz)
        sched_utc = sched_est.astimezone(timezone.utc)
        slots.append(sched_utc)

        slot_idx += 1
        if slot_idx >= slots_per_day:
            slot_idx = 0
            current_day += 1

    return slots


def get_pending_clips() -> List[Dict[str, Any]]:
    """Returns list of clips in Final_Clip/ that have not yet been uploaded."""
    tracker = load_tracker()
    pending = []

    final_dir = settings.final_clip_dir
    if not final_dir.exists():
        return []

    mp4_files = sorted(list(final_dir.glob("*.mp4")))
    for mp4 in mp4_files:
        base_name = mp4.stem
        json_file = final_dir / f"{base_name}.json"

        # Check if already uploaded
        if base_name in tracker:
            continue

        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}
        else:
            meta = {}

        pending.append({
            "name": base_name,
            "mp4_path": mp4,
            "json_path": json_file,
            "meta": meta
        })

    return pending


def upload_and_schedule(
    youtube,
    clip: Dict[str, Any],
    publish_at: datetime
) -> str:
    """Uploads a video to YouTube and sets it as scheduled."""
    mp4_path: Path = clip["mp4_path"]
    meta: Dict[str, Any] = clip["meta"]

    # Title: Clean + #Shorts tag
    raw_title = meta.get("title", clip["name"])
    if "#Shorts" not in raw_title and "#shorts" not in raw_title:
        title = f"{raw_title[:85]} #Shorts"
    else:
        title = raw_title[:100]

    # Description: CTA + hashtags
    description = meta.get("description", "")
    mandatory_cta = "Watch KreekCraft on YouTube and Twitch"
    if mandatory_cta not in description:
        description = f"{description.strip()}\n\n{mandatory_cta}"

    hashtags = meta.get("hashtags", ["#Shorts", "#GTA6", "#KreekCraft"])
    tags_clean = [t.lstrip("#") for t in hashtags]

    full_description = f"{description}\n\n" + " ".join(hashtags)

    # Format publishAt to ISO 8601 with 'Z'
    publish_iso = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "snippet": {
            "title": title,
            "description": full_description,
            "tags": tags_clean,
            "categoryId": "20",  # Gaming category
        },
        "status": {
            "privacyStatus": "private",  # Must be private to set publishAt
            "publishAt": publish_iso,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        str(mp4_path),
        mimetype="video/mp4",
        chunksize=1024*1024*4,
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"    Uploading {mp4_path.name}: {pct}%", end="\r")

    video_id = response.get("id")
    return video_id


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Shorts Auto-Scheduler via Official YouTube Data API."
    )
    parser.add_argument("--days", type=int, default=9, help="Number of days to distribute clips across (default: 9 for safe 5-clip/day pacing)")
    parser.add_argument("--limit", type=int, default=0, help="Max clips to upload in this run (0 = all pending)")
    parser.add_argument("--dry-run", action="store_true", help="Print schedule preview without uploading")

    args = parser.parse_args()

    pending = get_pending_clips()
    if not pending:
        print("\nNo pending clips found in data/Final_Clip/! All clips are already uploaded.")
        return

    if args.limit and args.limit > 0:
        clips_to_process = pending[:args.limit]
    else:
        clips_to_process = pending

    timestamps = generate_schedule_timestamps(len(clips_to_process), days=args.days)

    print("\n" + "=" * 65)
    print(" 🎬 YOUTUBE SHORTS OFFICIAL SCHEDULER")
    print(f" Total Clips to Schedule : {len(clips_to_process)}")
    print(f" Distributed Over        : {args.days} Days (US Peak Hours EST)")
    print(f" Daily Pacing            : ~{len(clips_to_process) // args.days + 1} clips/day")
    print("=" * 65)

    if args.dry_run:
        print("\n[DRY RUN PREVIEW]")
        for i, (clip, dt) in enumerate(zip(clips_to_process, timestamps), start=1):
            est_str = dt.astimezone(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %I:%M %p EST")
            print(f" {i:2d}. {clip['mp4_path'].name:30} -> {est_str}")
        print("\nDry run complete. No videos uploaded.")
        return

    # Authenticate with YouTube API
    youtube = get_authenticated_service()
    tracker = load_tracker()

    print("\nStarting automated upload & scheduling...")
    success_count = 0

    for i, (clip, dt) in enumerate(zip(clips_to_process, timestamps), start=1):
        est_str = dt.astimezone(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %I:%M %p EST")
        print(f"\n[{i}/{len(clips_to_process)}] {clip['name']}")
        print(f"  • Title       : {clip['meta'].get('title', 'Short')[:60]}...")
        print(f"  • Scheduled For: {est_str}")

        try:
            video_id = upload_and_schedule(youtube, clip, dt)
            print(f"  ✓ Uploaded! YouTube URL: https://youtu.be/{video_id}")

            tracker[clip["name"]] = {
                "video_id": video_id,
                "scheduled_est": est_str,
                "scheduled_utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "uploaded_at": datetime.now(timezone.utc).isoformat()
            }
            save_tracker(tracker)
            success_count += 1

        except HttpError as e:
            print(f"  ✗ YouTube API Error: {e}")
            if "uploadLimitExceeded" in str(e):
                print("\n[!] Reached YouTube daily upload quota limit. Run again tomorrow!")
                break
        except Exception as e:
            print(f"  ✗ Unexpected Error: {e}")

    print("\n" + "=" * 65)
    print(f" Finished! Successfully scheduled {success_count}/{len(clips_to_process)} clips on YouTube.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
