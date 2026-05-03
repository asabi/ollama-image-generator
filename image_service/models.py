"""Model discovery + catalog of well-known pullable models.

Capabilities come from Ollama's /api/show response:
  - "image" capability  → image-generation model
  - "completion"        → text model usable for prompt enhancement

We probe each installed model with /api/show and cache the result by
(name, modified_at). Cache invalidates automatically when a model is
re-pulled (Ollama updates modified_at).

The "catalog" lists well-known names that users might want to pull. Catalog
entries that aren't installed are surfaced in the dropdown with installed=False
so the UI can show a Pull button.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass

import httpx

log = logging.getLogger(__name__)

# Curated lists of known pullable models. The installed set is fully dynamic;
# this catalog only exists so the UI can suggest variants users haven't pulled
# yet. Add/remove entries freely — the app doesn't depend on these names.
IMAGE_CATALOG: list[str] = [
    "x/z-image-turbo:latest",
    "x/z-image-turbo:fp8",
    "x/z-image-turbo:bf16",
    "x/flux2-klein:latest",
    "x/flux2-klein:4b",
    "x/flux2-klein:9b",
]

TEXT_CATALOG: list[str] = [
    "gemma4:31b",
    "gemma4:e4b",
    "qwen3:30b",
    "qwen3.5:latest",
    "llama3.3:latest",
]


@dataclass
class ModelInfo:
    name: str
    installed: bool
    capability: str   # "image" | "text" | "unknown"
    parameter_size: str | None = None
    quantization_level: str | None = None
    family: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# Cache: {(name, modified_at): /api/show response dict}
_show_cache: dict[tuple[str, str], dict] = {}


def _ollama_base() -> str:
    base = os.environ.get("OLLAMA_BASE_URL")
    if not base:
        raise RuntimeError("OLLAMA_BASE_URL is not set")
    return base.rstrip("/")


def _show(name: str, modified_at: str) -> dict | None:
    """Return /api/show output for a model, cached by (name, modified_at)."""
    key = (name, modified_at)
    if key in _show_cache:
        return _show_cache[key]
    try:
        r = httpx.post(
            f"{_ollama_base()}/api/show",
            json={"model": name},
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("show(%s) failed: %s", name, e)
        return None
    _show_cache[key] = data
    return data


def _classify(show: dict) -> tuple[str, str | None, str | None, str | None]:
    """Return (capability, parameter_size, quantization_level, family)."""
    caps = [c.lower() for c in (show.get("capabilities") or [])]
    details = show.get("details") or {}
    if "image" in caps:
        cap = "image"
    elif "completion" in caps:
        cap = "text"
    else:
        cap = "unknown"
    return (
        cap,
        details.get("parameter_size") or None,
        details.get("quantization_level") or None,
        details.get("family") or None,
    )


def list_models() -> dict:
    """Return {image_models, text_models, default_image_model, default_text_model}.

    Installed models come from /api/tags + /api/show capability probes.
    Catalog entries that aren't installed are appended with installed=False.
    """
    base = _ollama_base()
    r = httpx.get(f"{base}/api/tags", timeout=5.0)
    r.raise_for_status()
    tags = r.json().get("models", [])

    image_results: list[ModelInfo] = []
    text_results: list[ModelInfo] = []
    seen: set[str] = set()

    for entry in tags:
        name = entry.get("name") or entry.get("model")
        if not name:
            continue
        modified = entry.get("modified_at", "")
        show = _show(name, modified)
        if show is None:
            continue
        cap, psize, qlevel, family = _classify(show)
        info = ModelInfo(
            name=name,
            installed=True,
            capability=cap,
            parameter_size=psize,
            quantization_level=qlevel,
            family=family,
        )
        seen.add(name)
        if cap == "image":
            image_results.append(info)
        elif cap == "text":
            text_results.append(info)
        # "unknown" capability models are dropped from both lists

    # Add catalog entries that aren't installed
    for name in IMAGE_CATALOG:
        if name not in seen:
            image_results.append(ModelInfo(name=name, installed=False, capability="image"))
            seen.add(name)
    for name in TEXT_CATALOG:
        if name not in seen:
            text_results.append(ModelInfo(name=name, installed=False, capability="text"))
            seen.add(name)

    # Installed first, then alphabetical
    sort_key = lambda m: (not m.installed, m.name)  # noqa: E731
    image_results.sort(key=sort_key)
    text_results.sort(key=sort_key)

    return {
        "image_models": [m.to_dict() for m in image_results],
        "text_models": [m.to_dict() for m in text_results],
        "default_image_model": os.environ.get("IMAGE_MODEL"),
        "default_text_model": os.environ.get("ENHANCE_MODEL"),
    }


def stream_pull(model: str):
    """Yield raw NDJSON dicts from Ollama's /api/pull as they arrive.

    Each dict is one of:
      {"status": "pulling manifest"}
      {"status": "downloading", "digest": "...", "total": N, "completed": M}
      {"status": "verifying sha256 digest"}
      {"status": "writing manifest"}
      {"status": "success"}
    On error, Ollama returns {"error": "..."}.
    """
    import json

    base = _ollama_base()
    with httpx.stream(
        "POST",
        f"{base}/api/pull",
        json={"model": model, "stream": True},
        timeout=None,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                log.warning("non-JSON line from /api/pull: %r", line)
