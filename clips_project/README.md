# Kick Stream Auto-Clipper (FastAPI Service)

An automated AI-powered video pipeline that takes a **Kick stream link** (or VOD) and produces **finished, edited vertical clips (reels) ready for upload**.

---

## 1. Features

- **Automated Download**: Fetches Kick VOD or stream using `yt-dlp`.
- **Audio Extraction & Chunking**: Splits audio into 5-minute chunks with 10-second overlap to stay within Groq limits.
- **Accurate Transcription**: Transcribes with Groq Whisper API (`whisper-large-v3-turbo`) and merges into global timestamps with overlap deduplication.
- **AI Highlight Detection**: LLM identifies viral hooks, reactions, fails, and clutch moments (15-60s) with viral scores (1-10), titles, captions, and hashtags. Supports custom **Creator Briefs (`briefs/brief.md`)** to enforce creator-specific guidelines.
- **Creator Branding & Logo**: Automatically scales and overlays creator logo watermark (`briefs/logo.png`) at the bottom of the video if present.
- **Frame-Accurate Cuts**: FFmpeg clips snapped to word/sentence boundaries with safety padding.
- **Viral Reel Editing**: Converts to 9:16 vertical (1080x1920, 30fps), dynamic blurred background, burned-in sleek small subtitles (size 42), and loudness normalization (-14 LUFS).
- **One-Command Cleanup**: `python delete.py -y` cleans all cached clips, downloads, transcripts, and logs while preserving folder structures.
- **1:1 Paired Output in `data/Final_Clip/`**: Each final clip has a matching `.mp4` and `.json` with the exact same base name (e.g. `stream123_01_s9.mp4` and `stream123_01_s9.json`) for seamless downstream upload automation.

---

## 2. Project Structure

```
kick-clipper/
├── venv/                       # Virtual environment (inside project)
├── .env                        # GROQ_API_KEY=...
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── delete.py                   # One-click data cleanup script
├── briefs/                     # Creator assets & instructions
│   ├── brief.md                # Creator rules and stream guidelines
│   └── logo.png                # (Optional) Creator watermark logo
├── app/
│   ├── main.py                 # FastAPI service entry point
│   ├── config.py               # Settings and directory configurations
│   ├── schemas.py              # Pydantic models (Job, Highlight, ClipMetadata)
│   ├── jobs.py                 # Background job queue and persistence manager
│   ├── api/
│   │   ├── jobs_routes.py      # /jobs endpoints
│   │   └── clips_routes.py     # /clips endpoints
│   └── pipeline/
│       ├── runner.py           # Pipeline runner & progress callback
│       ├── prompts.py          # LLM prompt templates
│       ├── downloader.py       # Step 1: yt-dlp downloader
│       ├── audio.py            # Step 2: ffmpeg audio extraction & chunking
│       ├── transcribe.py       # Steps 3-4: Groq Whisper transcription & merge
│       ├── highlights.py       # Step 5: Groq LLM highlight discovery
│       ├── clipper.py          # Step 6: ffmpeg word-boundary clip cutting
│       └── editor.py           # Step 7: 9:16 reel rendering & captions
├── cli.py                      # Standalone CLI runner
└── data/
    ├── downloads/              # Full downloaded stream videos
    ├── audio/                  # Extracted full audio
    ├── chunks/                 # 5-minute audio chunks (temporary)
    ├── transcripts/            # Full transcript JSONs with timestamps
    ├── highlights/             # Identified highlights JSON
    ├── clips/                  # Raw cut clips (intermediate)
    ├── jobs/                   # Job status JSON files
    └── Final_Clip/             # FINAL OUTPUT: .mp4 and matching .json
```

---

## 3. Setup & Installation

### Step 1: Clone or navigate to the project
```bash
cd clips_project
```

### Step 2: Create & Activate Virtual Environment
Inside the project root:

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On Windows (CMD):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment
Copy `.env.example` to `.env` and insert your free Groq API key:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
```

### Step 5: Verify FFmpeg
Make sure `ffmpeg` and `ffprobe` are installed on your system PATH:
```bash
ffmpeg -version
```

---

## 4. Running the Service

Start the FastAPI application with Uvicorn:
```bash
uvicorn app.main:app --reload --port 8000
```

Interactive OpenAPI Swagger UI is available at:
`http://localhost:8000/docs`

---

## 5. API Endpoints & Usage

### 1. Health Check
```bash
curl -X GET http://localhost:8000/health
```
Response:
```json
{
  "status": "ok",
  "ffmpeg_available": true,
  "groq_api_key_configured": true,
  "version": "1.0.0"
}
```

### 2. Submit a Clipping Job
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "kick_url": "https://kick.com/video/example-vod-id",
    "max_clips": 0,
    "min_score": 7,
    "layout": "blur"
  }'
```
*(Tip: Set `"max_clips": 0` or omit it to extract ALL qualifying viral clips from a 1–3 hr stream)*
Response (`202 Accepted`):
```json
{
  "job_id": "a1b2c3d4",
  "status": "queued",
  "message": "Job successfully enqueued and will run in the background."
}
```

### 3. Check Job Status
```bash
curl -X GET http://localhost:8000/jobs/a1b2c3d4
```
Response:
```json
{
  "job_id": "a1b2c3d4",
  "kick_url": "https://kick.com/video/example-vod-id",
  "status": "running",
  "stage": "transcribing",
  "progress": 35,
  "error": null,
  "failed_clips": [],
  "clips": [],
  "created_at": "2026-11-19T16:00:00Z",
  "updated_at": "2026-11-19T16:02:15Z"
}
```

### 4. List All Jobs
```bash
curl -X GET http://localhost:8000/jobs
```

### 5. List Finished Clips
```bash
curl -X GET http://localhost:8000/clips
```
Response:
```json
[
  {
    "name": "example_01_s9",
    "title": "He did NOT expect that 😂",
    "description": "Streamer loses his mind after an insane clutch! #kick #funny",
    "hashtags": ["#kick", "#funny", "#clips"],
    "video_file": "example_01_s9.mp4",
    "score": 9,
    "duration": 34.5,
    "video_url": "/clips/example_01_s9/video",
    "metadata_url": "/clips/example_01_s9"
  }
]
```

### 6. Download / Stream Final Video
```bash
curl -O -J http://localhost:8000/clips/example_01_s9/video
```

---

## 6. Standalone CLI Usage

You can also run the full pipeline directly from the command line:

```bash
python cli.py "https://kick.com/video/example-vod-id" --max-clips 5 --min-score 7 --layout blur
```

Options:
- `--max-clips INT`: Max clips to produce (default: 10).
- `--min-score INT`: Minimum viral rating from 1 to 10 (default: 7).
- `--layout blur|crop`: Layout mode (`blur` for 9:16 blurred background, `crop` for 9:16 center crop).
- `--force`: Re-run stages even if intermediate files exist.
- `--keep-temp`: Keep temporary 5-min audio chunk files.

---

## 7. Output in `data/Final_Clip/`

All ready-to-upload reels and metadata are saved side-by-side in `data/Final_Clip/` with the exact same base name:
```
data/Final_Clip/
├── video123_01_s9.mp4
├── video123_01_s9.json
├── video123_02_s8.mp4
└── video123_02_s8.json
```

Example `video123_01_s9.json`:
```json
{
  "title": "He did NOT expect that 😂",
  "description": "Streamer completely lost his mind live on stream! Wait for the ending 🔥",
  "hashtags": [
    "#kick",
    "#streamer",
    "#gaming",
    "#funny",
    "#reels"
  ],
  "video_file": "video123_01_s9.mp4",
  "source_url": "https://kick.com/video/...",
  "source_start": 1245.3,
  "source_end": 1279.8,
  "score": 9,
  "reason": "Loud reaction to an unexpected win, strong hook and payoff",
  "duration": 34.5,
  "created_at": "2026-11-19T21:45:00Z"
}
```
