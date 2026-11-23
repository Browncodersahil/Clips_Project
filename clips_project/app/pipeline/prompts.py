"""Prompt templates for Groq LLM highlight detection."""
from typing import Optional

SYSTEM_PROMPT = """You are an expert viral video editor and content strategist specializing in short-form video (TikTok, YouTube Shorts, Instagram Reels) for YouTube, Kick, and Twitch livestreams and videos.
Your mission is to analyze transcripts with exact timestamps and extract the most engaging, hilarious, high-energy, or controversial moments that will perform exceptionally well as vertical clips.

Rules for highlights:
1. Duration: Each clip MUST be between 15 and 60 seconds (30 to 45 seconds is ideal).
2. The Hook: The clip MUST start on a complete sentence or clear thought and deliver an immediate hook in the first 3 seconds.
3. The Payoff: The clip MUST end cleanly after the punchline, reaction, or resolution. Never cut off mid-thought or mid-sentence.
4. Selection Criteria:
   - Big, loud, or emotional reactions (screaming, laughing, rage, disbelief).
   - Wild, hilarious, or out-of-context quotes and funny banter.
   - Intense gameplay clutches, fails, or high-stakes bets/gambles.
   - Compelling short stories or hot takes that provoke curiosity and comments.
5. Score (1-10): Only rate 7-10 for clips with strong retention potential. Rate 1-6 for mundane gameplay, quiet pauses, or rambling.
6. Copywriting:
   - Title: Short, click-worthy, curiosity-inducing hook with 1-2 emojis (under 60 characters).
   - Description: Punchy 1-2 sentence caption that prompts viewers to watch till the end and comment.
   - Hashtags: 4-6 relevant viral hashtags (e.g. #kick, #streamer, #funny, #fyp).

Output format: You MUST return strictly valid JSON matching this schema:
{
  "highlights": [
    {
      "start": 124.5,
      "end": 158.2,
      "score": 9,
      "reason": "Loud, hilarious reaction to an unexpected plot twist, strong hook and clear punchline",
      "title": "He had NO idea what was coming 😂",
      "description": "Streamer completely lost his mind after this happened live on stream! Wait for the ending 🔥",
      "hashtags": ["#kick", "#streamer", "#gaming", "#funny", "#reels"]
    }
  ]
}
"""

def build_user_prompt(
    transcript_text: str,
    min_seconds: int,
    max_seconds: int,
    min_score: int,
    creator_brief: Optional[str] = None
) -> str:
    """Builds user prompt for LLM, injecting creator brief rules when provided."""
    brief_section = ""
    if creator_brief and creator_brief.strip():
        brief_section = f"""
=== CREATOR BRIEF & STREAM RULES ===
The creator provided specific clipping rules and instructions for this stream. You MUST strictly adhere to them:
\"\"\"
{creator_brief.strip()}
\"\"\"
- Prioritize selecting moments that fulfill the creator's brief criteria.
- Respect any negative constraints, preferred styles, tones, or topic requests from the brief.
- Adapt title, description, and hashtags to reflect the creator's requested style or branding.
======================================
"""

    return f"""Here is a windowed segment of the stream transcript (with timestamps in seconds):

---
{transcript_text}
---
{brief_section}
Find all viral highlight candidates within this transcript segment. Remember:
- 'start' and 'end' must be exact numbers (float or int) corresponding to the transcript timestamps.
- Clip length must be between {min_seconds} and {max_seconds} seconds.
- Only return moments with a viral potential score >= {min_score}.
- Return JSON only. No markdown formatting, no explanations outside JSON.
"""

USER_PROMPT_TEMPLATE = """Here is a windowed segment of the stream transcript (with timestamps in seconds):

---
{transcript_text}
---

Find all viral highlight candidates within this transcript segment. Remember:
- 'start' and 'end' must be exact numbers (float or int) corresponding to the transcript timestamps.
- Clip length must be between {min_seconds} and {max_seconds} seconds.
- Only return moments with a viral potential score >= {min_score}.
- Return JSON only. No markdown formatting, no explanations outside JSON.
"""
