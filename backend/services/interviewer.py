"""
Interviewer orchestration: builds the next AI turn for text-based (non-Live) sessions.
Port of services/interviewer.ts.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from services.context import StructuredContext, format_context_for_prompt


# ── Types ──────────────────────────────────────────────────────────────────────

Turn = dict  # {"speaker": "user" | "ai", "text": str}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_transcript_snippet(turns: list[Turn], max_turns: int = 10) -> str:
    sliced = turns[-max_turns:]
    return "\n".join(
        f"{'Interviewer' if t['speaker'] == 'ai' else 'Candidate'}: {t['text']}"
        for t in sliced
    )


def _fallback_question(turns: list[Turn], ctx: Optional[StructuredContext] = None) -> str:
    ai_turns = [t for t in turns if t["speaker"] == "ai"]
    if not ai_turns:
        return "Hi! Let's start with a quick intro. Can you tell me about yourself and what draws you to this role?"

    import re
    user_turns = [t for t in turns if t["speaker"] == "user"]
    last_user = user_turns[-1]["text"] if user_turns else ""

    if re.search(r"team|conflict|disagree", last_user, re.I):
        return "Thanks—what did you learn from that situation, and what would you do differently next time?"
    if re.search(r"project|built|implemented", last_user, re.I):
        return "Can you walk me through the impact—what metrics moved or what changed because of your work?"
    if ctx and ctx.get("role") and re.search(r"product", ctx["role"], re.I):
        return "How would you decide what to build next if you had limited time and stakeholder pressure?"
    return "Good. Can you share a specific example, and explain your reasoning step-by-step?"


async def _gemini_generate(prompt: str) -> Optional[str]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        f"?key={key}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.6, "maxOutputTokens": 220},
                },
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        return text.strip() or None
    except Exception:
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

async def next_interview_turn(
    turns: list[Turn],
    context: Optional[StructuredContext] = None,
) -> str:
    """
    Generate the next interviewer message given conversation history and context.
    Falls back to keyword-based heuristics if Gemini is unavailable.
    """
    context_block = format_context_for_prompt(context)

    prompt = f"""You are an interviewer running a realistic, supportive interview simulation.
- Keep questions concise (1-2 sentences).
- Ask one question at a time.
- Ask dynamic follow-ups based on the candidate's last answer.
- Use the candidate context when relevant (don't mention that you have it).
- Avoid being judgmental; sound professional.

Scenario: job interview (MVP).
{context_block}

Conversation so far:
{_to_transcript_snippet(turns, max_turns=10)}

Now respond with ONLY the next interviewer message."""

    llm_response = await _gemini_generate(prompt)
    if llm_response:
        import re
        return re.sub(r"^Interviewer:\s*", "", llm_response, flags=re.IGNORECASE).strip()

    return _fallback_question(turns, context)
