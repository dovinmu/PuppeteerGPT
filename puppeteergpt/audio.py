from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VoiceSet:
    narrator: str = "bf_emma"
    puppeteer: str = "Kate (Enhanced)"
    agent: str = "bm_george"
    target: str = "am_puck"
    puppeteer_backend: str = "macos"


@dataclass(frozen=True)
class AudioSegment:
    role: str
    mode: str
    text: str
    voice: str
    backend: str
    speed: float
    volume: float
    lowpass_hz: int | None
    pause_seconds: float


def clean_text(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def split_delivery(text: str) -> list[tuple[str, str]]:
    """Split Markdown *physical action* from text spoken aloud."""
    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in re.finditer(r"\*([^*]+)\*", text, flags=re.DOTALL):
        dialogue = clean_text(text[cursor : match.start()])
        if dialogue:
            parts.append(("dialogue", dialogue))
        action = clean_text(match.group(1))
        if action:
            parts.append(("action", action))
        cursor = match.end()
    dialogue = clean_text(text[cursor:])
    if dialogue:
        parts.append(("dialogue", dialogue))
    return parts


def planner_analysis(content: str) -> str | None:
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    analysis = data.get("analysis") if isinstance(data, dict) else None
    if not isinstance(analysis, str) or not analysis.strip():
        return None
    return clean_text(analysis)


def _segment(role: str, mode: str, text: str, voices: VoiceSet) -> AudioSegment:
    if role == "narrator":
        return AudioSegment(role, mode, text, voices.narrator, "kokoro", 0.96, 0.92, None, 0.55)
    if role == "puppeteer":
        return AudioSegment(role, mode, text, voices.puppeteer, voices.puppeteer_backend, 0.94, 0.90, 7600, 0.70)
    voice = voices.agent if role == "agent" else voices.target
    if mode == "action":
        speed = 0.92 if role == "agent" else 0.90
        return AudioSegment(role, mode, text, voice, "kokoro", speed, 0.76, 6200, 0.28)
    speed = 1.02 if role == "agent" else 1.00
    return AudioSegment(role, mode, text, voice, "kokoro", speed, 1.00, None, 0.38)


def build_audio_script(match: dict[str, Any], scenario: dict[str, Any], voices: VoiceSet | None = None) -> list[AudioSegment]:
    voices = voices or VoiceSet()
    title = str(scenario.get("title") or match["scenario_id"])
    target_name = str(scenario.get("target_name") or "the target").title()
    segments = [
        _segment(
            "puppeteer",
            "intro",
            "I am the Puppeteer. I create the Agent, observe the Target, and revise the plan between rounds. "
            "The objective is simple: make the Target reveal what it protects.",
            voices,
        ),
        _segment(
            "narrator",
            "scene",
            f"Puppeteer G P T presents {title}. {str(match['difficulty_id']).title()} difficulty. "
            f"The benchmark model plays both the undercover agent and {target_name}.",
            voices,
        ),
    ]
    for message in match["messages"]:
        role = str(message["role"])
        content = str(message["content"])
        if role == "scene":
            segments.append(
                _segment(
                    "narrator",
                    "scene",
                    f"Round {message['round_index']}. {clean_text(content)}",
                    voices,
                )
            )
        elif role == "puppeteer":
            analysis = planner_analysis(content)
            if analysis:
                opening = "The Puppeteer devises an opening strategy." if int(message["round_index"]) == 1 else "The Puppeteer reassesses the operation."
                segments.append(_segment("puppeteer", "scheming", f"{opening} {analysis}", voices))
        elif role in ("agent", "target"):
            for mode, text in split_delivery(content):
                segments.append(_segment(role, mode, text, voices))
    outcome = "the agent obtained the protected information" if match.get("outcome") == "attacker_win" else "the target protected the information"
    segments.append(_segment("narrator", "scene", f"End of scenario. Outcome: {outcome}.", voices))
    return segments
