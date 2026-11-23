---                                                                                                                                                                           
                                                                                                                                                                                  
    ## ⚡ Quick Start                                                                                                                                                             
                                                                                                                                                                                  
    ### 1. Prerequisites                                                                                                                                                          
    Ensure you have **Python 3.10+** and **FFmpeg** installed on your system.                                                                                                     
                                                                                                                                                                                  
    ```bash                                                                                                                                                                       
    # Ubuntu / Debian                                                                                                                                                             
    sudo apt update && sudo apt install ffmpeg                                                                                                                                    
                                                                                                                                                                                  
    # macOS                                                                                                                                                                       
    brew install ffmpeg                                                                                                                                                           
                                                                                                                                                                                  
    # Windows                                                                                                                                                                     
    winget install Gyan.FFmpeg                                                                                                                                                    
                                                                                                                                                                                  
  2. Clone & Setup                                                                                                                                                                
                                                                                                                                                                                  
    # Clone the repository                                                                                                                                                        
    git clone https://github.com/yourusername/kick-clipper.git                                                                                                                    
    cd kick-clipper                                                                                                                                                               
                                                                                                                                                                                  
    # Create & activate virtual environment                                                                                                                                       
    python3 -m venv .venv                                                                                                                                                         
    source .venv/bin/activate    # On Windows: .venv\Scripts\activate                                                                                                             
                                                                                                                                                                                  
    # Install dependencies                                                                                                                                                        
    pip install -r requirements.txt                                                                                                                                               
    playwright install chromium                                                                                                                                                   
                                                                                                                                                                                  
  3. Configure Keys                                                                                                                                                               
                                                                                                                                                                                  
  Copy .env.example to .env:                                                                                                                                                      
                                                                                                                                                                                  
    cp .env.example .env                                                                                                                                                          
                                                                                                                                                                                  
  Add your free Groq Cloud API Key https://console.groq.com/:                                                                                                                     
                                                                                                                                                                                  
    GROQ_API_KEY=gsk_your_groq_api_key_here                                                                                                                                       
  ──────                                                                                                                                                                          
  🎮 How to Run                                                                                                                                                                   
                                                                                                                                                                                  
  Option A: Interactive CLI (Fastest)                                                                                                                                             
                                                                                                                                                                                  
    python cli.py "https://kick.com/video/your-stream-vod-id"                                                                                                                     
                                                                                                                                                                                  
  Option B: FastAPI Backend                                                                                                                                                       
                                                                                                                                                                                  
  Launch the microservice server:                                                                                                                                                 
                                                                                                                                                                                  
    uvicorn app.main:app --reload --port 8000                                                                                                                                     
                                                                                                                                                                                  
  Open http://localhost:8000/docs to test endpoints via Swagger UI.                                                                                                               
  ──────                                                                                                                                                                          
  📡 Auto-Pilot Distribution                                                                                                                                                      
                                                                                                                                                                                  
  🔴 YouTube Shorts (API + Smart Scheduling)                                                                                                                                      
                                                                                                                                                                                  
  Uploads rendered clips directly to YouTube Shorts mapped to US Peak Engagement Hours (EST):                                                                                     
                                                                                                                                                                                  
    # Authenticate YouTube (one-time OAuth)                                                                                                                                       
    python yt_uploader.py --auth                                                                                                                                                  
                                                                                                                                                                                  
    # Upload latest ready clips                                                                                                                                                   
    python yt_uploader.py                                                                                                                                                         
                                                                                                                                                                                  
    # Schedule all unreleased clips at peak viral intervals                                                                                                                       
    python yt_uploader.py --schedule                                                                                                                                              
                                                                                                                                                                                  
  📸 Instagram Reels (Playwright Stealth Engine)                                                                                                                                  
                                                                                                                                                                                  
  Zero API restrictions. Uses persistent browser profiles with anti-bot measures:                                                                                                 
                                                                                                                                                                                  
    # First-time login (saves session cookie profile)                                                                                                                             
    python insta_uploader.py --login                                                                                                                                              
                                                                                                                                                                                  
    # Verify authentication state                                                                                                                                                 
    python insta_uploader.py --check                                                                                                                                              
                                                                                                                                                                                  
    # Fire upload on all new clips with metadata                                                                                                                                  
    python insta_uploader.py                                                                                                                                                      
  ──────                                                                                                                                                                          
  🧠 Creator Briefs Intelligence                                                                                                                                                  
  
  Tailor the AI to your specific streamer archetype! Edit briefs/brief.md:
  
    # Creator Brief: The Speed Demon
    - Target Audience: Gen-Z gamers, competitive FPS enthusiasts
    - Clip Tone: High energy, clutches, desk slams, unexpected fails
    - Clip Duration: 20-45 seconds
    - Subtitle Rules: High contrast, emphasize loud moments with UPPERCASE
    - Avoid: In-game menus, idle waiting screens, stream breaks
  
  The LLaMA-3 detection engine reads this brief before analyzing transcripts to ensure 100% brand alignment.
  ──────
  📦 Output Format                                                                                                                                                                
  
  Every clip generated in data/Final_Clip/ is 1:1 paired:
  
    data/Final_Clip/
    ├── stream_vod_01_s9.mp4   # 1080x1920 9:16 Video, Subtitled, Watermarked
    └── stream_vod_01_s9.json  # Metadata: Title, Description, Tags & Viral Score
  
  Example JSON:
  
    {
      "title": "THE MOST INSANE 1v4 CLUTCH 🔥",                                                                                                                                   
      "score": 9.5,
      "caption": "Bro really pulled this off with 1 HP left... 💀 #gaming #clutch #kickstreamer",                                                                                 
      "tags": ["gaming", "kick", "clutch", "viral", "highlights"]
    }
  ──────
  🤝 Contributing                                                                                                                                                                 
  
  Contributions are welcome! Please feel free to submit a Pull Request.
  
  1. Fork the Project
  2. Create your Feature Branch (git checkout -b feature/CrazyFeature)
  3. Commit your Changes (git commit -m 'Add some CrazyFeature')
  4. Push to the Branch (git push origin feature/CrazyFeature)
  5. Open a Pull Request
  ──────
  Crafted with ❤ for content creators & streamers.
  
  ⭐ Leave a star if this saves you 10+ hours a week! ⭐                                                                                                                          
  ```──────
  What makes this README stand out:
  
  1. Interactive Badges: Real links to Python, FastAPI, Groq, Playwright, and FFmpeg.
  2. Visual Flowchart: Explains the entire pipeline in 2 seconds.
  3. Comprehensive: Highlights the AI pipeline, the Creator Briefs, YouTube peak-hour scheduling, and Instagram stealth Playwright automation.
  4. Copy-Paste Ready: Fits your exact repo structure, scripts, and endpoints.
