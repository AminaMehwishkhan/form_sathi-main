"""
Small helper for the auto language detection / bilingual behavior (Feature 2).

Most translation work happens inline as part of the vision prompt (Gemma
returns both explanation_english and explanation_urdu already). This module
is for the smaller, ad-hoc case: translating a user's free-typed answer or
a follow-up question on demand, via a cheap text-only Gemma call.
"""

from __future__ import annotations
from utils.gemma import DEFAULT_MODEL, OLLAMA_HOST
import requests
import json

_URDU_RANGE = range(0x0600, 0x06FF)


def looks_urdu(text: str) -> bool:
    if not text:
        return False
    urdu_chars = sum(1 for ch in text if ord(ch) in _URDU_RANGE)
    return urdu_chars > max(1, len(text) * 0.2)


def translate(text: str, target: str = "urdu", model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST) -> str:
    """Best-effort translation via Gemma text generation. Falls back to the
    original text if Ollama isn't reachable — never blocks the UI."""
    if not text.strip():
        return text

    prompt = (
        f"Translate the following text into {target}. "
        f"Return ONLY the translated text, nothing else.\n\nText: {text}"
    )
    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("response", text).strip()
    except (requests.RequestException, json.JSONDecodeError):
        return text
