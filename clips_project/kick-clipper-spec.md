# Project: Kick Stream Auto-Clipper (FastAPI Service)

> **Instructions for the coding agent:** Build this project step by step, following the phases in Section 11. After each phase, test it on a short video and confirm the acceptance criteria before moving on. Ask before adding dependencies not listed here. Keep the code modular, with one file per responsibility. **Everything (virtual environment, code, data, config) must live inside the single project folder. Do not install anything globally.**

---

## 1. Goal

Run a **FastAPI service**. You send it a **Kick stream link** (live or VOD), and it automatically produces **finished, edited vertical clips (reels) that are ready to upload**.

**Final output:** everything ready to upload goes in one folder, `data/Final_Clip/`. Each reel is an `.mp4` (9:16, 1080x1920, with captions) plus a `.json` with the **exact same base name** (e.g. `abc123_01_s9.mp4` and `abc123_01_s9.json`), holding the title, description, and hashtags. This 1:1 pairing lets a future uploader pick up each video and its metadata by name.

**Out of scope for now:** uploading to any platform (Instagram, YouTube, TikTok), scheduling, and account handling. That will be built separately later.

---

## 2. Setup (do this first, all inside the project folder)

1. Create the project folder `kick-clipper/` and work inside it.
2. Create the virtual environment **inside the project folder**:
   ```bash
   python -m venv venv
   ```
3. Activate it:
   - Windows (PowerShell): `venv\Scripts\Activate.ps1`
   - Windows (cmd): `venv\Scripts\activate.bat`
   - macOS / Linux: `source venv/bin/activate`
4. Install dependencies **only inside the venv**:
   ```bash
   pip install -r requirements.txt
   ```
5. Create `.env` from `.env.example` and set `GROQ_API_KEY`.
6. Check that system `ffmpeg` is installed (`ffmpeg -version`). If it isn't, tell the user how to install it. Don't try to install system packages silently.
7. Create all `data/` subfolders automatically on startup if they don't exist.
8. Add a `.gitignore` containing `venv/`, `.env`, `data/`, `__pycache__/`.
9. Run the service:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Interactive docs at `http://localhost:8000/docs`.

---

## 3. Pipeline

```
POST /jobs {kick_url}
   │
   ▼
[1] Download video              (yt-dlp + ffmpeg)
   │
   ▼
[2] Extract audio, split into 5-min chunks (with overlap)
   │
   ▼
[3] Transcribe each chunk       (Groq Whisper API)
   │
   ▼
[4] Merge transcripts → global timestamps
   │
   ▼
[5] Find highlights             (Groq LLM → JSON)
   │
   ▼
[6] Cut exact clips from the ORIGINAL video (ffmpeg)
   │
   ▼
[7] Edit into reel: 9:16, captions, loudness normalize
   │
   ▼
data/Final_Clip/  →  ready-to-upload .mp4 + same-name .json
```

The pipeline runs as a **background job**. The API returns immediately with a `job_id`, and the client checks progress by polling.

---

## 4. Tech Stack

- Python 3.11+
- **FastAPI** + **uvicorn** (service)
- `yt-dlp`, `ffmpeg` (system install), `ffmpeg-python` or `subprocess`
- `groq` Python SDK (Whisper transcription + LLM)
- `moviepy` for editing (or direct ffmpeg where faster)
- `pydantic` / `pydantic-settings` (models and config), `python-dotenv`, `tqdm`, `tenacity` (retries)
- Optional: `opencv-python` for smart cropping

**Note:** the API is **Groq** (groq.com), not Grok (xAI). Free API key from console.groq.com. Store as `GROQ_API_KEY` in `.env`.

`requirements.txt` should list all of the above with versions pinned after the first successful install.

---

## 5. Project Structure

```
kick-clipper/
├── venv/                       # virtual environment (inside the project)
├── .env                        # GROQ_API_KEY=...
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── app/
│   ├── main.py                 # FastAPI app, startup, CORS, router include
│   ├── config.py               # all settings in one place
│   ├── schemas.py              # pydantic models (requests, responses, Segment, Highlight, Job)
│   ├── jobs.py                 # job manager: create, run in background, track status/progress
│   ├── api/
│   │   ├── jobs_routes.py      # /jobs endpoints
│   │   └── clips_routes.py     # /clips endpoints
│   └── pipeline/
│       ├── runner.py           # runs all stages in order, reports progress
│       ├── downloader.py       # step 1
│       ├── audio.py            # step 2
│       ├── transcribe.py       # steps 3-4
│       ├── highlights.py       # step 5 (+ prompts.py)
│       ├── clipper.py          # step 6
│       └── editor.py           # step 7
├── cli.py                      # optional: python cli.py <kick_url> (uses the same runner)
└── data/
    ├── downloads/              # original stream videos
    ├── audio/                  # full extracted audio per stream
    ├── chunks/                 # 5-min audio chunks (temporary)
    ├── transcripts/            # Whisper transcript JSON per stream
    ├── highlights/             # highlight JSON per stream (LLM output)
    ├── clips/                  # raw cut clips, unedited (intermediate)
    ├── jobs/                   # one JSON file per job (status, progress, result)
    └── Final_Clip/             # FINAL: edited .mp4 + same-name .json (title, description, hashtags)
```

---

## 6. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service check; also reports whether ffmpeg and `GROQ_API_KEY` are available |
| `POST` | `/jobs` | Start a job. Body: `{ "kick_url": "...", "max_clips": 10, "min_score": 7, "layout": "blur" }`. Returns `202` with `{ "job_id": "...", "status": "queued" }` |
| `GET` | `/jobs/{job_id}` | Job status: `status`, current `stage`, `progress` (0-100), `error` (if failed), and `clips` (list of final clip names once done) |
| `GET` | `/jobs` | List all jobs, newest first |
| `DELETE` | `/jobs/{job_id}` | Cancel a queued/running job (best effort) or remove a finished job record |
| `GET` | `/clips` | List all clips in `Final_Clip/` with their metadata |
| `GET` | `/clips/{name}` | Metadata JSON for one clip (`name` = shared base name) |
| `GET` | `/clips/{name}/video` | Stream/download the `.mp4` (`FileResponse`) |

**Job stages:** `queued → downloading → extracting_audio → transcribing → finding_highlights → clipping → editing → done` (or `failed`).

**Job behavior:**
- Run the pipeline in the background (thread pool or background worker), never blocking the request handler.
- **One job at a time** by default (the rest wait in a queue), to protect the Groq free-tier limits and CPU. Make the limit configurable (`MAX_CONCURRENT_JOBS`).
- Persist job state to `data/jobs/<job_id>.json` so status survives a restart. On startup, mark any jobs left in a running state as `failed` with a note like "interrupted".
- Validate the URL (must be a Kick link) and return `422` with a clear message if not.
- Use proper status codes (`404` unknown job/clip, `409` for conflicts, etc.).
- Run uvicorn with a **single worker**, since job state is managed in-process.

---

## 7. Module Requirements

### 7.1 `pipeline/downloader.py`
- Input: Kick URL. Output: path to the video file.
- Use `yt-dlp` (Python API or subprocess). Best quality up to 1080p, merged to MP4.
- **VOD:** download the full file.
- **Live:** record in segments (e.g. 5-min files) so processing can start before the stream ends. Do this in the optional live phase; start with VOD only.
- Skip the download if the file already exists (cache).
- Clear error messages for an invalid link or an offline stream.

### 7.2 `pipeline/audio.py`
- Extract audio from the video with ffmpeg: **mono, 16 kHz, FLAC or MP3** (keeps each chunk under Groq's ~25 MB file limit). Save the full audio in `data/audio/`.
- Split into **5-minute chunks with a 10-second overlap**, saved in `data/chunks/`.
- Return a list of `{chunk_path, offset_seconds}`. The offset is needed to map timestamps back to the full video.

### 7.3 `pipeline/transcribe.py`
- Send each chunk to Groq: model `whisper-large-v3-turbo` (configurable), `response_format="verbose_json"`, with **word-level and segment-level timestamps**.
- Add the chunk offset to every timestamp → **global timestamps**.
- Remove duplicate text caused by the overlap (drop segments that start before the previous chunk's end).
- Retry with exponential backoff on rate limits (429) and network errors.
- Save the transcript to `data/transcripts/<video_id>.json`. If it exists, reuse it (cache).
- Process chunks in parallel with a small worker limit (default 2-3) to stay inside free-tier limits.

### 7.4 `pipeline/highlights.py`
- Input: the full transcript with timestamps.
- Because transcripts can be long, send it to the LLM in **windows** (e.g. 10-15 minutes of text at a time).
- Use a Groq LLM (e.g. `llama-3.3-70b-versatile`, configurable) with **JSON-only output**.
- Each highlight:
  ```json
  {
    "start": 1245.3,
    "end": 1281.9,
    "score": 9,
    "reason": "Loud reaction to an unexpected win, strong hook and payoff",
    "title": "He did NOT expect that 😂",
    "description": "Streamer loses it after an unexpected win. Wait for the ending!",
    "hashtags": ["#kick", "#funny", "#clips"]
  }
  ```
- Prompt rules (keep the prompt in `prompts.py` so it is easy to edit):
  - Clip length **15-60 seconds** (30-45 ideal)
  - Must **start on a complete sentence** with a **strong hook in the first 3 seconds**
  - Must end after the payoff or punchline, not mid-thought
  - Good moments: big reactions, funny or controversial lines, clear stories, hype/clutch moments
  - Return `score` from 1-10
- After collecting results:
  - **Dedupe** overlapping or near-duplicate clips (keep the higher score)
  - Drop anything below `MIN_SCORE` (default 7)
  - Keep at most `MAX_CLIPS` (default 10 per stream, configurable)
- Validate JSON output with pydantic. Retry once if the output is malformed.
- Save to `data/highlights/<video_id>.json`.

### 7.5 `pipeline/clipper.py`
- Cut each highlight from the **original video** with ffmpeg.
- Add ~1 second of padding before and after.
- **Snap** the start/end to the nearest Whisper segment boundary so the clip never cuts mid-word.
- Re-encode for frame-accurate cuts (don't use stream copy).
- Output to `data/clips/`.

### 7.6 `pipeline/editor.py`
- Convert each raw clip into a finished reel:
  - **9:16 vertical, 1080x1920, 30 fps, H.264 + AAC**
  - Layout (configurable, default = "blur background"): the original video centered, with a blurred and zoomed copy of itself filling the background
  - Alternative layout: center-crop to 9:16 (zoomed on the streamer/action)
  - **Burned-in captions** from word-level timestamps: large, bold, white with a dark outline, positioned in the lower-middle, with the active word highlighted (karaoke style) if feasible; otherwise 2-4 words at a time
  - Normalize loudness (ffmpeg `loudnorm`, target about -14 LUFS)
  - Optional (off by default): watermark/logo, intro hook text, background music
- Save the final `.mp4` and its `.json` **both in `data/Final_Clip/` with the exact same base name**, e.g. `<video_id>_<index>_s<score>.mp4` and `<video_id>_<index>_s<score>.json`.
- The JSON must contain: `title`, `description`, `hashtags` (list), `video_file` (the matching mp4 filename), `source_url`, `source_start`, `source_end`, `score`.
- Only finished reels go in `Final_Clip/`. Raw cuts stay in `clips/`, and audio, chunks, transcripts and highlight files each stay in their own folder.
- Write the JSON only after the mp4 renders successfully, so there are never orphan files.

### 7.7 `pipeline/runner.py`
- A single function `run_pipeline(job, params, progress_callback)` that runs the stages in order and updates the job's stage and progress after each step (e.g. weighted: download 15%, audio 5%, transcribe 35%, highlights 10%, clipping 10%, editing 25%).
- Each stage is **resumable**: if its output already exists, skip it (a `force` option redoes it).
- One failed clip must **not** fail the whole job: log it and continue. The job ends as `done` with a list of any clips that failed.
- Clean up large intermediate files (chunks) after success, unless `keep_temp` is set.

---

## 8. `config.py` Settings

Load from `.env` with `pydantic-settings`.

```python
GROQ_API_KEY = ""            # from .env
CHUNK_SECONDS = 300          # 5 minutes
CHUNK_OVERLAP_SECONDS = 10
WHISPER_MODEL = "whisper-large-v3-turbo"
LLM_MODEL = "llama-3.3-70b-versatile"
MIN_SCORE = 7
MAX_CLIPS = 10
MIN_CLIP_SECONDS = 15
MAX_CLIP_SECONDS = 60
CLIP_PADDING_SECONDS = 1.0
OUTPUT_RESOLUTION = (1080, 1920)
OUTPUT_FPS = 30
LAYOUT = "blur"              # "blur" or "crop"
TRANSCRIBE_WORKERS = 2
MAX_CONCURRENT_JOBS = 1
DATA_DIR = "data"
```

---

## 9. Error Handling and Logging

- Use Python `logging` (info-level progress, debug for details). Write the log to `data/run.log`.
- On startup, fail early (and report in `/health`) if `ffmpeg` is not installed or `GROQ_API_KEY` is missing.
- Never leak the API key in logs or responses.
- Return clean JSON error responses from the API (no raw stack traces).

---

## 10. Known Risks

- **Permission / copyright:** only use content you have the streamer's permission to clip, or your own streams.
- **Groq free-tier limits:** rate limits and daily audio caps. Use backoff and caching so reruns don't waste quota.
- **Kick changes:** Kick may change its stream format. Keep `yt-dlp` updated.
- **Clip quality:** highlight picking will need prompt tuning.
- **Disk space:** full streams are large. Clean up after processing.
- **In-process jobs:** a server restart interrupts running jobs. This is acceptable for now, since state is saved and the job can be resubmitted (cached stages make a rerun fast).

---

## 11. Build Phases (follow in order)

**Phase 0: Setup**
Create the project folder, the `venv` inside it, `requirements.txt`, `.env.example`, `.gitignore`, the folder structure, and a FastAPI app with `GET /health`.
*Acceptance:* `uvicorn app.main:app` starts from inside the venv, `/health` responds, and all `data/` folders are created.

**Phase 1: Download + audio + transcription**
Build `downloader.py`, `audio.py`, `transcribe.py`.
*Acceptance:* a short (5-10 min) Kick VOD produces a transcript JSON with correct global timestamps.

**Phase 2: Highlights**
Build the highlight schemas and `highlights.py`.
*Acceptance:* valid, deduped highlight JSON with sensible 15-60 second ranges.

**Phase 3: Clipping**
Build `clipper.py`.
*Acceptance:* clips start and end on sentence boundaries, with no mid-word cuts, and play correctly.

**Phase 4: Reel editing**
Build `editor.py`.
*Acceptance:* 1080x1920 MP4 with readable captions and normalized audio, plus a same-name JSON, both in `Final_Clip/`.

**Phase 5: Runner + API**
Build `runner.py`, `jobs.py`, and the `/jobs` and `/clips` endpoints.
*Acceptance:* `POST /jobs` with a Kick link returns a `job_id`; polling `GET /jobs/{id}` shows stages and progress; on completion `GET /clips` lists the finished reels and `/clips/{name}/video` plays one.

**Phase 6: Polish**
Add `cli.py`, resume/caching checks, logging, and the README (setup steps from Section 2 and example `curl` calls).

**Phase 7 (optional): Live mode**
Process segments while the stream is still running.

---

## 12. Future Work (not part of this build)

- Auto-upload to Instagram, YouTube Shorts, TikTok (it will read pairs from `Final_Clip/`)
- Queue + scheduler (1-2 reels every 60-90 minutes)
- A review step to approve or reject clips before finalizing
- Audio-energy / chat-spike scoring to improve highlight ranking
- Face-tracking auto-crop
