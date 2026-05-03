"""Image generation via `ollama run` with the experimental image-gen flags.

`ollama run --width W --height H --seed S [--negative N] [--steps S] MODEL "<prompt>"`

writes a PNG to the current working directory and prints
    Image saved to: <name>.png

We run it in a private temp dir, parse stderr in real time for the model's
"Generating XX% ▕...▏ N/N" progress line, then move the file into our managed
images dir under a UUID filename.

`generate_image_streaming` is a generator that yields ProgressEvent objects
as the model progresses, then a final GenerationResult when the file lands.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Iterator

from PIL import Image

from .db import IMAGES_DIR, THUMBS_DIR, ensure_dirs

log = logging.getLogger(__name__)

ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]")
PROGRESS_RE = re.compile(r"Generating\s+(\d+)%.*?(\d+)\s*/\s*(\d+)")
SAVED_RE = re.compile(r"Image saved to:\s*(.+\.png)\s*$", re.IGNORECASE)
THUMB_MAX = (320, 320)


@dataclass
class ProgressEvent:
    percent: int
    step: int
    total: int


@dataclass
class GenerationResult:
    image_id: str
    filename: str        # UUID.png in IMAGES_DIR
    thumbnail: str       # UUID.png in THUMBS_DIR
    image_path: Path
    thumb_path: Path


def _make_thumbnail(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        im.thumbnail(THUMB_MAX)
        im.save(dst, format="PNG", optimize=True)


def _stream_lines(stream, q: Queue, label: str) -> None:
    """Read raw bytes from `stream` and push de-ANSI'd lines onto `q`.

    ollama's progress bar uses \\r to update in place, so we split on either
    \\n or \\r — otherwise we'd get a single mega-line at end-of-process.
    """
    buf = b""
    while True:
        b = stream.read(1)
        if not b:
            break
        if b in (b"\n", b"\r"):
            line = ANSI_RE.sub(b"", buf).decode("utf-8", "ignore").strip()
            if line:
                q.put((label, line))
            buf = b""
        else:
            buf += b
    if buf:
        line = ANSI_RE.sub(b"", buf).decode("utf-8", "ignore").strip()
        if line:
            q.put((label, line))


def generate_image_streaming(
    model: str,
    prompt: str,
    width: int,
    height: int,
    seed: int,
    negative_prompt: str | None = None,
    steps: int | None = None,
    timeout_seconds: int = 600,
) -> Iterator[ProgressEvent | GenerationResult]:
    """Generator: yields ProgressEvent events while ollama runs, then yields a
    final GenerationResult once the PNG is on disk.

    Raises RuntimeError on any failure.
    """
    ensure_dirs()
    image_id = uuid.uuid4().hex
    final_filename = f"{image_id}.png"
    final_image = IMAGES_DIR / final_filename
    final_thumb = THUMBS_DIR / final_filename

    cmd: list[str] = [
        "ollama", "run",
        "--width", str(width),
        "--height", str(height),
        "--seed", str(seed),
    ]
    if negative_prompt and negative_prompt.strip():
        cmd += ["--negative", negative_prompt.strip()]
    if steps is not None:
        cmd += ["--steps", str(steps)]
    cmd += [model, prompt]

    with tempfile.TemporaryDirectory(prefix="ollama_imggen_") as tmp:
        workdir = Path(tmp)
        log.info(
            "ollama run %dx%d seed=%d steps=%s neg=%r model=%s prompt=%r",
            width, height, seed, steps, bool(negative_prompt), model, prompt,
        )
        proc = subprocess.Popen(
            cmd, cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        q: Queue[tuple[str, str]] = Queue()
        threading.Thread(
            target=_stream_lines, args=(proc.stdout, q, "out"), daemon=True
        ).start()
        threading.Thread(
            target=_stream_lines, args=(proc.stderr, q, "err"), daemon=True
        ).start()

        last_percent = -1
        saved_str: str | None = None

        # Pump events until the process exits AND the queue has drained.
        while proc.poll() is None or not q.empty():
            try:
                _label, line = q.get(timeout=0.1)
            except Empty:
                continue

            m = PROGRESS_RE.search(line)
            if m:
                pct = int(m.group(1))
                if pct != last_percent:
                    last_percent = pct
                    yield ProgressEvent(pct, int(m.group(2)), int(m.group(3)))
                continue

            m = SAVED_RE.search(line)
            if m:
                saved_str = m.group(1).strip().strip('"').strip("'")

        rc = proc.wait(timeout=5)
        if rc != 0:
            # drain remaining stderr for the error message
            tail = []
            while True:
                try:
                    tail.append(q.get_nowait()[1])
                except Empty:
                    break
            raise RuntimeError(
                f"ollama exited {rc}. Last lines:\n" + "\n".join(tail[-20:])
            )

        # Locate the PNG. Prefer the saved-to path; fall back to scanning.
        candidate: Path | None = None
        if saved_str:
            p = Path(saved_str)
            if not p.is_absolute():
                p = workdir / p
            if p.exists():
                candidate = p
        if candidate is None:
            pngs = list(workdir.glob("*.png"))
            if len(pngs) == 1:
                candidate = pngs[0]
        if candidate is None:
            raise RuntimeError(
                f"Could not locate generated PNG in {workdir} "
                f"(saved-line: {saved_str!r})"
            )

        shutil.move(str(candidate), str(final_image))

    _make_thumbnail(final_image, final_thumb)

    yield GenerationResult(
        image_id=image_id,
        filename=final_filename,
        thumbnail=final_filename,
        image_path=final_image,
        thumb_path=final_thumb,
    )
