"""Prompt enhancement via a local text model (over LiteLLM → local Ollama).

Any model that advertises the "completion" capability via /api/show works.
The default is configured in .env (ENHANCE_MODEL); the UI lets the user
pick any installed text model — discovery lives in models.py.
"""

from __future__ import annotations

import logging
import os
from typing import Iterator

import httpx
import litellm

from .styles import STYLE_BY_ID

log = logging.getLogger(__name__)


def _ollama_base() -> str:
    base = os.environ.get("OLLAMA_BASE_URL")
    if not base:
        raise RuntimeError("OLLAMA_BASE_URL is not set")
    return base.rstrip("/")


def default_enhance_model() -> str:
    name = os.environ.get("ENHANCE_MODEL")
    if not name:
        raise RuntimeError("ENHANCE_MODEL is not set")
    return name


SYSTEM_PROMPT = (
    "You are a prompt-engineering assistant for a text-to-image diffusion model. "
    "Given a short user idea and a target visual style, expand the idea into a "
    "single, vivid, comma-separated image prompt of 30-60 words. "
    "Keep the user's intent. Add concrete visual detail: subject, composition, "
    "lighting, mood, palette, camera/medium where it fits the style. "
    "Do NOT add commentary, headings, quotes, or markdown. Output only the prompt."
)


def _build_messages(user_prompt: str, style_id: str) -> list[dict]:
    style = STYLE_BY_ID.get(style_id)
    if style is None:
        raise ValueError(f"Unknown style id: {style_id!r}")
    user_msg = (
        f"Style: {style.enhance_hint}\n"
        f"User idea: {user_prompt.strip()}\n\n"
        "Write the enhanced image prompt now."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]


def enhance_prompt_stream(
    user_prompt: str, style_id: str, model: str | None = None
) -> Iterator[str]:
    """Yield gemma's response one chunk at a time. Caller is responsible for
    joining + cleaning when the stream finishes (use clean_enhanced)."""
    chosen = model or default_enhance_model()
    messages = _build_messages(user_prompt, style_id)
    resp = litellm.completion(
        model=f"ollama/{chosen}",
        api_base=_ollama_base(),
        messages=messages,
        temperature=0.8,
        stream=True,
    )
    for chunk in resp:
        delta = chunk["choices"][0].get("delta") or {}
        text = delta.get("content") or ""
        if text:
            yield text


def clean_enhanced(text: str) -> str:
    """Strip wrapper quotes / 'Prompt:' lead-ins gemma sometimes emits."""
    t = text.strip()
    if len(t) >= 2 and t[0] in "\"'`" and t[-1] == t[0]:
        t = t[1:-1].strip()
    for lead in ("Prompt:", "prompt:", "Enhanced prompt:"):
        if t.startswith(lead):
            t = t[len(lead):].strip()
            break
    return t
