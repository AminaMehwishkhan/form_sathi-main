"""
Thin client around a local Ollama server running Gemma 4 (vision-capable, e.g. gemma4:e2b).

Kept deliberately dependency-light (just `requests`) so it's easy to demo offline.
"""

from __future__ import annotations
import base64
import json
import re
import requests
from typing import Optional

from utils.prompts import (
    FORM_ANALYSIS_SYSTEM_PROMPT,
    FORM_ANALYSIS_USER_PROMPT,
    FIELD_HELP_PROMPT_TEMPLATE,
    RETRY_LOWER_CONFIDENCE_NOTE,
)

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:e2b"
REQUEST_TIMEOUT = 300


class GemmaError(Exception):
    """Raised when Ollama/Gemma can't be reached or returns something unusable."""


def _image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def check_ollama_alive(host: str = OLLAMA_HOST) -> bool:
    """Quick health check so the UI can show a friendly 'Ollama not running' message
    instead of a stack trace."""
    try:
        r = requests.get(f"{host}/api/tags", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _extract_json(raw_text: str) -> dict:
    """Gemma sometimes wraps JSON in markdown fences or adds stray text despite
    instructions. Strip that defensively before parsing."""
    text = raw_text.strip()
    text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text.strip()).strip()

    # If there's leading/trailing chatter, grab the outermost {...}
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)

    return json.loads(text)


def analyze_form_image(
    image_bytes: bytes,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
    retry_hint: bool = False,
) -> dict:
    """
    Send a form image to Gemma 4 Vision via Ollama and get back the parsed
    FormAnalysis-shaped dict (see schemas/field_schema.py).

    Raises GemmaError on connection failure or unparsable output.
    """
    prompt = FORM_ANALYSIS_USER_PROMPT
    if retry_hint:
        prompt = f"{RETRY_LOWER_CONFIDENCE_NOTE}\n\n{prompt}"

    payload = {
        "model": model,
        "prompt": prompt,
        "system": FORM_ANALYSIS_SYSTEM_PROMPT,
        "images": [_image_to_base64(image_bytes)],
        "format": "json",
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,  # low temp: we want consistent, faithful extraction, not creativity
        },
    }

    try:
        resp = requests.post(f"{host}/api/generate", json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise GemmaError(
            f"Could not reach Ollama at {host}. Is it running? (`ollama serve`, "
            f"and `ollama pull {model}`). Original error: {e}"
        ) from e

    data = resp.json()
    raw_text = data.get("response", "")

    try:
        parsed = _extract_json(raw_text)
    except (json.JSONDecodeError, TypeError) as e:
        raise GemmaError(
            f"Gemma returned output that wasn't valid JSON. Raw output:\n{raw_text[:800]}"
        ) from e

    return parsed


def explain_field(
    label: str,
    help_text: str,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
) -> dict:
    """Ask Gemma (text-only, cheap/fast) to re-explain a specific field in simpler words."""
    prompt = FIELD_HELP_PROMPT_TEMPLATE.format(label=label, help_text=help_text or "none given")

    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.3},
    }

    try:
        resp = requests.post(f"{host}/api/generate", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return _extract_json(data.get("response", "{}"))
    except (requests.RequestException, json.JSONDecodeError):
        # Non-fatal — fall back to whatever help_text we already had.
        return {"urdu": help_text, "english": help_text}
