#!/usr/bin/env python3
"""
Automated Instagram Reels US Peak Hour Scheduler.
Monitors US EST peak traffic windows (11:30 AM - 10:00 PM EST) and posts
scheduled reels matching the exact YouTube Shorts timetable.
"""

import os
import sys
from pathlib import Path

# Auto-switch to project virtual environment if run via system python3
PROJECT_ROOT = Path(__file__).resolve().parent
_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and sys.prefix != str(PROJECT_ROOT / ".venv"):
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

import argparse
import datetime
import json
import logging
import time
from typing import List, Dict, Any, Tuple

from app.config import settings
from insta_uploader import (
    get_pending_clips,
    upload_reel_to_instagram,
    load_tracker,
    save_tracker,
    PROFILE_DIR
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("insta_scheduler")

# US Peak EST Slots (Matching YouTube schedule)
US_PEAK_SLOTS_EST = [
    (11, 30),  # 11:30 AM EST (US Lunch / East Coast waking)
    (14, 0),   # 02:00 PM EST (West Coast noon / East Coast afternoon)
    (16, 30),  # 04:30 PM EST (School / Work ending)
    (18, 30),  # 06:30 PM EST (Peak Prime Evening)
    (20, 30),  # 08:30 PM EST (Peak Prime Evening)
    (22, 0),   # 10:00 PM EST (Late night mobile browsing)
]

# EST is UTC-5
EST_OFFSET = datetime.timezone(datetime.timedelta(hours=-5), name="EST")


def get_current_est() -> datetime.datetime:
    return datetime.datetime.now(EST_OFFSET)


def get_next_slots(count: int = 10) -> List[datetime.datetime]:
    now_est = get_current_est()
    slots = []
    current_date = now_est.date()

    for day_offset in range(14):
        slot_date = current_date + datetime.timedelta(days=day_offset)
        for hour, minute in US_PEAK_SLOTS_EST:
            slot_dt = datetime.datetime(
                slot_date.year, slot_date.month, slot_date.day,
                hour, minute, tzinfo=EST_OFFSET
            )
            # Give a 5-minute grace window if we are right on the edge
            if slot_dt > now_est - datetime.timedelta(minutes=5):
                slots.append(slot_dt)
                if len(slots) >= count:
                    return slots
    return slots


def format_slot_times(slot_est: datetime.datetime) -> str:
    local_dt = slot_est.astimezone()
    est_str = slot_est.strftime("%Y-%m-%d %I:%M %p EST")
    local_str = local_dt.strftime("%I:%M %p Local")
    return f"{est_str} (≈ {local_str})"


def display_schedule():
    pending = get_pending_clips()
    if not pending:
        print("\nAll clips are already uploaded! Nothing pending.")
        return

    slots = get_next_slots(min(len(pending), 12))
    print("\n" + "=" * 72)
    print(" ⏰ INSTAGRAM REELS US PEAK-HOUR SCHEDULE")
    print(f" Current US Time: {get_current_est().strftime('%Y-%m-%d %I:%M:%S %p EST')}")
    print(f" Current Local  : {datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
    print(f" Total Pending  : {len(pending)} reels")
    print("=" * 72)

    for i, (clip, slot) in enumerate(zip(pending[:len(slots)], slots), start=1):
        diff = slot - get_current_est()
        hours, remainder = divmod(int(diff.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        time_until = f"in {hours}h {minutes}m" if diff.total_seconds() > 0 else "READY NOW"
        print(f"[{i:02d}] {clip['name']}")
        print(f"     Title    : {clip.get('meta', {}).get('title', 'Reel')[:40]}...")
        print(f"     Scheduled: {format_slot_times(slot)} -> {time_until}")
        print("-" * 72)


def run_scheduler_daemon(dry_run: bool = False):
    from playwright.sync_api import sync_playwright

    print("\n" + "=" * 72)
    print(" 🤖 INSTAGRAM REELS AUTOMATED BACKGROUND SCHEDULER")
    print(" Running continuous loop to post reels at US Peak Hours.")
    print(" Press Ctrl+C at any time to safely stop.")
    print("=" * 72)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for lock in PROFILE_DIR.glob("Singleton*"):
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass

    while True:
        pending = get_pending_clips()
        if not pending:
            logger.info("All reels have been posted! Scheduler finished.")
            break

        next_slot = get_next_slots(1)[0]
        now_est = get_current_est()
        seconds_wait = (next_slot - now_est).total_seconds()

        next_clip = pending[0]
        logger.info(
            f"Next Reel: {next_clip['name']} scheduled for {format_slot_times(next_slot)}"
        )

        if seconds_wait > 60:
            wait_m = int(seconds_wait // 60)
            logger.info(f"Sleeping for {wait_m} minutes until target US traffic slot...")
            # Sleep in intervals so Ctrl+C or interruptions respond promptly
            while seconds_wait > 60:
                sleep_chunk = min(seconds_wait - 60, 120)
                time.sleep(sleep_chunk)
                now_est = get_current_est()
                seconds_wait = (next_slot - now_est).total_seconds()

        # Target slot reached! Launch browser and upload
        logger.info(f"Target slot reached! Initiating upload for {next_clip['name']}...")
        if dry_run:
            logger.info("[Dry Run] Simulating successful post.")
            time.sleep(5)
            continue

        tracker = load_tracker()
        success = False

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR.resolve()),
                    headless=True,
                    viewport={"width": 1280, "height": 850},
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox"
                    ]
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                success = upload_reel_to_instagram(page, next_clip)
                browser.close()
        except Exception as e:
            logger.error(f"Error during scheduled upload: {e}")

        if success:
            tracker[next_clip["name"]] = {
                "uploaded_to": "Instagram",
                "posted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "scheduled_slot_est": next_slot.strftime("%Y-%m-%d %I:%M %p EST")
            }
            save_tracker(tracker)
            logger.info(f"✓ {next_clip['name']} successfully posted to Instagram!")
            # Cool down for 5 minutes to pass the current slot window
            time.sleep(300)
        else:
            logger.warning(f"Upload failed for {next_clip['name']}. Will retry in 10 minutes.")
            time.sleep(600)


def main():
    parser = argparse.ArgumentParser(
        description="Instagram Reels Automated US Peak Hour Scheduler"
    )
    parser.add_argument("--daemon", action="store_true", help="Run as background scheduler daemon")
    parser.add_argument("--dry-run", action="store_true", help="Simulate schedule without actual uploads")
    parser.add_argument("--post-now", action="store_true", help="Post the very next clip immediately")

    args = parser.parse_args()

    if args.post_now:
        pending = get_pending_clips()
        if not pending:
            print("No clips pending!")
            return
        from insta_uploader import main as uploader_main
        sys.argv = [sys.argv[0], "--limit", "1"]
        uploader_main()
        return

    if args.daemon:
        run_scheduler_daemon(dry_run=args.dry_run)
    else:
        display_schedule()
        print("\n💡 Run as a background daemon to auto-post at each US slot:")
        print("   python3 insta_scheduler.py --daemon\n")
        print("💡 Or post the next clip immediately right now:")
        print("   python3 insta_scheduler.py --post-now\n")


if __name__ == "__main__":
    main()
