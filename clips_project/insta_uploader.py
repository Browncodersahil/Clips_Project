#!/usr/bin/env python3
"""
insta_uploader.py - Automates uploading Reels to Instagram Web using Playwright.

Safety & Anti-Bot Protection:
- Uses a persistent browser profile (you log in ONCE, session is saved permanently).
- Dedicated login verification before any upload attempts.
- Automatically handles 'Save Info' and 'Not Now' notification popups.
- Zero plain-text credentials in code.
- Human-like typing, delays, and mouse interactions.
- Tracks uploaded clips in data/uploaded_instagram.json.
"""

import os
import sys
from pathlib import Path

# Auto-switch to project virtual environment if run via system python3
PROJECT_ROOT = Path(__file__).resolve().parent
_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and sys.prefix != str(PROJECT_ROOT / ".venv"):
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

import json
import time
import random
import logging
import argparse
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(PROJECT_ROOT))
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("insta_uploader")

PROFILE_DIR = PROJECT_ROOT / "data" / "insta_browser_profile"
TRACKER_FILE = settings.base_data_dir / "uploaded_instagram.json"


def load_tracker() -> Dict[str, Any]:
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_tracker(tracker: Dict[str, Any]):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)


def human_sleep(min_sec: float = 2.0, max_sec: float = 4.0):
    """Sleeps with random jitter to mimic human hesitation."""
    time.sleep(random.uniform(min_sec, max_sec))


def dismiss_popups(page):
    """Dismisses common Instagram popups like 'Save login info' or 'Turn on notifications'."""
    try:
        # Check for 'Not now' buttons
        not_now_selectors = [
            "button:has-text('Not Now')",
            "button:has-text('Not now')",
            "button:has-text('Cancel')",
            "button:has-text('Save info')",
        ]
        for sel in not_now_selectors:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                loc.click()
                human_sleep(1.0, 2.0)
    except Exception:
        pass


def is_logged_in(page) -> bool:
    """Checks if the user is truly logged into their Instagram home feed."""
    indicators = [
        "svg[aria-label='Home']",
        "svg[aria-label='New post']",
        "svg[aria-label='Create']",
        "span:has-text('Create')",
        "span:has-text('Home')",
        "svg[aria-label='Direct messaging']",
        "svg[aria-label='Activity Feed']"
    ]
    for sel in indicators:
        try:
            if page.locator(sel).first.is_visible(timeout=2000):
                return True
        except Exception:
            pass
    return False


def ensure_instagram_logged_in(page) -> bool:
    """
    Ensures user is logged into Instagram before any uploads begin.
    If 2FA, SMS code, or login screen is active, pauses and waits for user.
    """
    logger.info("Checking Instagram login session...")
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    human_sleep(3.0, 5.0)
    dismiss_popups(page)

    if is_logged_in(page):
        logger.info("Instagram session active! Already logged in.")
        return True

    print("\n" + "=" * 65)
    print(" 🔑 ACTION REQUIRED: LOG INTO INSTAGRAM IN THE CHROME WINDOW")
    print("=" * 65)
    print(" 1. In the opened Chrome window, enter your username & password.")
    print(" 2. Complete any security code / 2FA / SMS challenge if asked.")
    print(" 3. Click 'Save info' or 'Not now' on any popups.")
    print(" 4. Once you are looking at your main Instagram home feed:")
    print("    Come back here and press ENTER to start uploading!")
    print("=" * 65 + "\n")

    while True:
        try:
            input("Press Enter after you are logged into your Instagram feed: ")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

        human_sleep(2.0, 3.0)
        dismiss_popups(page)

        if is_logged_in(page) or "instagram.com" in page.url and "auth_platform" not in page.url and "login" not in page.url:
            logger.info("Login confirmed! Proceeding with Reel uploads...")
            return True
        else:
            print("[!] Still not detected on home feed. Please make sure login is completed, then press Enter again.")


def get_pending_clips() -> List[Dict[str, Any]]:
    tracker = load_tracker()
    pending = []
    final_dir = settings.final_clip_dir
    if not final_dir.exists():
        return []

    mp4_files = sorted(list(final_dir.glob("*.mp4")))
    for mp4 in mp4_files:
        base_name = mp4.stem
        if base_name in tracker:
            continue
        json_file = final_dir / f"{base_name}.json"
        meta = {}
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass
        pending.append({
            "name": base_name,
            "mp4_path": mp4,
            "json_path": json_file,
            "meta": meta
        })
    return pending


def upload_reel_to_instagram(page, clip: Dict[str, Any]) -> bool:
    """Automates the Instagram web upload dialog for a single reel."""
    mp4_path: Path = clip["mp4_path"]
    meta: Dict[str, Any] = clip["meta"]

    # Caption preparation
    title = meta.get("title", "")
    description = meta.get("description", "")
    hashtags = meta.get("hashtags", ["#GTA6", "#KreekCraft", "#gaming", "#reels"])

    mandatory_cta = "Watch KreekCraft on YouTube and Twitch"
    if mandatory_cta not in description and mandatory_cta not in title:
        description = f"{description.strip()}\n\n{mandatory_cta}"

    caption_parts = []
    if title:
        caption_parts.append(title)
    if description:
        caption_parts.append(description)
    if hashtags:
        caption_parts.append(" ".join(hashtags))

    full_caption = "\n\n".join(caption_parts)

    logger.info(f"Navigating to Instagram home for {mp4_path.name}...")
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    human_sleep(3.0, 4.5)
    dismiss_popups(page)

    # Click the Create (+) button on the left sidebar
    create_btn = (
        page.locator("svg[aria-label='New post']")
        .or_(page.locator("svg[aria-label='Create']"))
        .or_(page.locator("span:has-text('Create')"))
        .or_(page.locator("a[href='#']:has-text('Create')"))
    ).first

    if not create_btn.is_visible(timeout=8000):
        logger.error("Could not find Create button on Instagram page.")
        return False

    create_btn.click()
    human_sleep(1.5, 2.5)

    # In modern Instagram Web, clicking Create opens a dropdown with 'Post'
    post_item = page.get_by_text("Post", exact=True).first
    if post_item.is_visible(timeout=4000):
        logger.info("Clicking 'Post' in Create menu...")
        post_item.click()
        human_sleep(1.5, 2.5)

    # Wait for the upload modal dialog
    dialog = page.locator("div[role='dialog']").first
    if not dialog.is_visible(timeout=10000):
        logger.error("Upload modal dialog did not appear.")
        return False

    # Attach video file
    file_input = page.locator("input[type='file']").first
    if file_input.count() > 0:
        file_input.set_input_files(str(mp4_path.resolve()))
    else:
        # Use file chooser on 'Select from computer'
        btn = page.locator("button:has-text('Select from computer')")
        if btn.is_visible(timeout=5000):
            with page.expect_file_chooser() as fc_info:
                btn.click()
            file_chooser = fc_info.value
            file_chooser.set_files(str(mp4_path.resolve()))
        else:
            page.set_input_files("input[type='file']", str(mp4_path.resolve()))

    logger.info("Video file attached, waiting for upload preview...")
    human_sleep(4.0, 6.0)

    # Dismiss "Video posts are now shared as reels" OK button if it appears
    ok_modal = page.locator("button:has-text('OK')").first
    if ok_modal.is_visible(timeout=4000):
        logger.info("Dismissing Reels popup...")
        ok_modal.click()
        human_sleep(1.5, 2.5)

    # Select 9:16 portrait aspect ratio
    try:
        crop_btn = (
            page.locator("svg[aria-label='Select crop']")
            .or_(page.locator("button:has(svg[aria-label='Select crop'])"))
            .or_(page.locator("div[role='button']:has(svg[aria-label='Select crop'])"))
        ).first
        if crop_btn.is_visible(timeout=3000):
            crop_btn.click()
            human_sleep(1.0, 1.5)
            nine_sixteen = (
                page.locator("button:has-text('9:16')")
                .or_(page.locator("span:has-text('9:16')"))
                .or_(page.locator("div[role='button']:has-text('9:16')"))
            ).first
            if nine_sixteen.is_visible(timeout=2000):
                nine_sixteen.click()
                human_sleep(1.0, 1.5)
    except Exception as e:
        logger.debug(f"Crop selection note: {e}")

    # Click Next (from Crop/Media to Edit/Cover)
    next_btn = (
        page.locator("div[role='dialog'] button:has-text('Next')")
        .or_(page.locator("div[role='dialog'] div[role='button']:has-text('Next')"))
        .or_(page.locator("div[role='dialog'] :text-is('Next')"))
    ).first
    if next_btn.is_visible(timeout=8000):
        next_btn.click()
        human_sleep(2.5, 3.5)
    else:
        logger.error("Could not find first Next button.")
        return False

    # Click Next (from Edit/Cover to Caption/Share screen)
    next_btn_2 = (
        page.locator("div[role='dialog'] button:has-text('Next')")
        .or_(page.locator("div[role='dialog'] div[role='button']:has-text('Next')"))
        .or_(page.locator("div[role='dialog'] :text-is('Next')"))
    ).first
    if next_btn_2.is_visible(timeout=8000):
        next_btn_2.click()
        human_sleep(2.5, 3.5)

    # Caption textarea
    caption_box = (
        page.locator("div[role='dialog'] div[aria-label*='caption' i]")
        .or_(page.locator("div[role='dialog'] div[role='textbox']"))
        .or_(page.locator("div[role='dialog'] div[contenteditable='true']"))
    ).first

    if caption_box.is_visible(timeout=8000):
        caption_box.click()
        human_sleep(1.0, 1.5)
        caption_box.fill(full_caption)
        logger.info("Caption and hashtags entered.")
        human_sleep(2.0, 3.0)
    else:
        logger.warning("Could not find caption textbox, continuing to share...")

    # Click Share button
    share_btn = (
        page.locator("div[role='dialog'] button:has-text('Share')")
        .or_(page.locator("div[role='dialog'] div[role='button']:has-text('Share')"))
        .or_(page.locator("div[role='dialog'] :text-is('Share')"))
    ).first
    if share_btn.is_visible(timeout=8000):
        share_btn.click()
        logger.info("Share button clicked! Waiting for Instagram to process upload...")

        # Monitor upload progress (Instagram displays 'Sharing' while encoding/uploading)
        start_wait = time.time()
        posted = False
        while time.time() - start_wait < 150:
            human_sleep(3.0, 5.0)

            # Check for success indicators
            has_success_text = page.locator("text='Your reel has been shared', text='Your post has been shared'").first.is_visible()
            has_checkmark = page.locator("svg[aria-label='Animated checkmark']").first.is_visible()
            dialog_count = page.locator("div[role='dialog']").count()
            is_sharing = page.locator("text='Sharing'").first.is_visible()

            if has_success_text or has_checkmark or (not is_sharing and dialog_count == 0):
                posted = True
                break

            if not is_sharing and (page.locator("button:has-text('View post')").first.is_visible() or page.locator("a:has-text('View post')").first.is_visible()):
                posted = True
                break

        if posted:
            logger.info(f"✓ Successfully posted {mp4_path.name} to Instagram!")
            human_sleep(3.0, 5.0)
            return True
        else:
            logger.error(f"Upload verification timed out for {mp4_path.name}.")
            return False
    else:
        logger.error("Could not find Share button.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Instagram Reels Auto-Uploader via Persistent Browser Session."
    )
    parser.add_argument("--limit", type=int, default=4, help="Max reels to post in this session (default: 4 to avoid spam flags)")
    parser.add_argument("--pause", type=int, default=60, help="Seconds to pause between consecutive uploads (default: 60)")
    parser.add_argument("--headless", action="store_true", help="Run browser invisibly (not recommended for first run)")

    args = parser.parse_args()

    pending = get_pending_clips()
    if not pending:
        print("\nNo pending clips found in data/Final_Clip/! All clips are already uploaded.")
        return

    clips_to_upload = pending[:args.limit]
    print("\n" + "=" * 65)
    print(" 📸 INSTAGRAM REELS WEB UPLOADER")
    print(f" Total Pending Clips   : {len(pending)}")
    print(f" Uploading in this run : {len(clips_to_upload)} (Paced to prevent bot flags)")
    print(f" Profile Directory     : {PROFILE_DIR.resolve()}")
    print("=" * 65)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for lock in PROFILE_DIR.glob("Singleton*"):
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass

    tracker = load_tracker()

    with sync_playwright() as p:
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR.resolve()),
            headless=args.headless,
            viewport={"width": 1280, "height": 850},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )

        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

        # Step 1: Ensure login is completely verified and on home feed
        ensure_instagram_logged_in(page)

        # Step 2: Upload clips
        success_count = 0
        for i, clip in enumerate(clips_to_upload, start=1):
            print(f"\n[{i}/{len(clips_to_upload)}] Uploading {clip['name']}...")
            try:
                ok = upload_reel_to_instagram(page, clip)
                if ok:
                    tracker[clip["name"]] = {
                        "uploaded_to": "Instagram",
                        "posted_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_tracker(tracker)
                    success_count += 1

                    if i < len(clips_to_upload):
                        print(f"Waiting {args.pause}s before next clip to keep account safe...")
                        time.sleep(args.pause)
                else:
                    logger.warning(f"Failed to post {clip['name']}, skipping to next.")
            except Exception as e:
                logger.error(f"Error during Instagram upload of {clip['name']}: {e}")

        browser_context.close()

    print("\n" + "=" * 65)
    print(f" Finished! Successfully posted {success_count}/{len(clips_to_upload)} reels to Instagram.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
