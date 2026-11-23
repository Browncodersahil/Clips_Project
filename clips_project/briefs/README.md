# Creator Briefs & Logo Assets

This directory contains creator-specific instructions and branding assets for your clipping pipeline.

---

### Files:

1. **`brief.md`**:
   - Write your stream guidelines, creator rules, do's & don'ts, and preferred topics here.
   - The Groq AI highlight finder reads this file and aligns its clip discovery, viral scoring, and title/caption generation to match these exact rules.
   - *If `brief.md` does not exist or is empty, the pipeline automatically falls back to standard viral highlight detection.*

2. **`logo.png` (or `.jpg`, `.jpeg`, `.webp`)**:
   - Place your creator or brand logo here (transparent PNG recommended).
   - The video editor scales the logo appropriately and places it centered at the bottom of every vertical reel.
   - *If no logo image exists in this folder, the video editor renders standard vertical clips without any logo watermark.*

---

### Captions:
- Captions are automatically formatted in a sleek, smaller size (`font_size: 42`) in the lower third with 3-word animated chunks for maximum readability without overlapping the bottom logo.
