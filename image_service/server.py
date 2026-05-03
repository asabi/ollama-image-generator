"""FastAPI server for the image-generation service."""

from __future__ import annotations

import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import db, enhance, models, ollama_client
from .styles import STYLES, build_full_prompt

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("image_service")


def _required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(
            f"Required env var {name} is missing. "
            "Copy .env.example to .env and fill it in."
        )
    return v


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("running migrations")
    db.migrate()
    # touch required env vars so we fail loudly on startup, not on first request
    _required("OLLAMA_BASE_URL")
    _required("IMAGE_MODEL")
    _required("ENHANCE_MODEL")
    log.info("ready")
    yield


app = FastAPI(title="Local Image Studio", lifespan=lifespan)

frontend_port = os.environ.get("FRONTEND_PORT", "5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- schemas ----------

class StyleOut(BaseModel):
    id: str
    label: str


class EnhanceIn(BaseModel):
    prompt: str = Field(min_length=1)
    style: str
    model: str | None = None


class GenerateIn(BaseModel):
    prompt: str = Field(min_length=1)
    style: str
    width: int = Field(ge=128, le=2048)
    height: int = Field(ge=128, le=2048)
    negative_prompt: str | None = None
    seed: int | None = None       # if set, lock the seed; if null, randomize per image
    steps: int | None = None      # let model default if null
    batch_count: int = Field(default=1, ge=1, le=4)
    image_model: str | None = None   # override IMAGE_MODEL env var for this call


class PullIn(BaseModel):
    model: str = Field(min_length=1)


class ImageOut(BaseModel):
    id: str
    filename: str
    thumbnail: str
    user_prompt: str
    full_prompt: str
    negative_prompt: str | None
    style: str
    width: int
    height: int
    seed: int | None
    steps: int | None
    model: str
    created_at: str


# ---------- routes ----------

@app.get("/api/styles", response_model=list[StyleOut])
def get_styles() -> list[StyleOut]:
    return [StyleOut(id=s.id, label=s.label) for s in STYLES]


@app.get("/api/models")
def get_models() -> dict:
    """Return image_models, text_models, and defaults — all derived from
    Ollama's /api/show capabilities, merged with our pull-catalog."""
    return models.list_models()


@app.post("/api/pull")
def post_pull(body: PullIn) -> StreamingResponse:
    """Stream the pull progress from Ollama's /api/pull through to the frontend."""

    def gen() -> Iterator[str]:
        try:
            for ev in models.stream_pull(body.model):
                # Ollama emits {"status":...} or {"error":...}; pass through verbatim.
                yield _ndjson(ev)
                if ev.get("error"):
                    return
        except Exception as e:
            log.exception("pull failed")
            yield _ndjson({"error": str(e)})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


@app.post("/api/enhance")
def post_enhance(body: EnhanceIn) -> StreamingResponse:
    """Stream gemma's enhancement token-by-token as NDJSON.

    Events:
      {"type":"chunk","text": "..."}
      {"type":"final","text": "<cleaned>", "model": "..."}
      {"type":"error","detail": "..."}
    """
    chosen = body.model or _required("ENHANCE_MODEL")

    def gen() -> Iterator[str]:
        try:
            buf: list[str] = []
            for chunk_text in enhance.enhance_prompt_stream(
                user_prompt=body.prompt, style_id=body.style, model=chosen
            ):
                buf.append(chunk_text)
                yield _ndjson({"type": "chunk", "text": chunk_text})
            cleaned = enhance.clean_enhanced("".join(buf))
            yield _ndjson({"type": "final", "text": cleaned, "model": chosen})
        except ValueError as e:
            yield _ndjson({"type": "error", "detail": str(e)})
        except Exception as e:
            log.exception("enhance failed")
            yield _ndjson({"type": "error", "detail": str(e)})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


SEED_MAX = 2**31 - 1  # ollama's --seed is an int flag; stay safely in int32 range


@app.post("/api/generate")
def post_generate(body: GenerateIn) -> StreamingResponse:
    """Stream generation progress as NDJSON.

    Events:
      {"type":"start","batch_count":N}
      {"type":"image_start","image_index":i,"seed":S}
      {"type":"progress","image_index":i,"percent":P,"step":s,"total":t}
      {"type":"image","image_index":i,"image":<ImageOut>}
      {"type":"done"}
      {"type":"error","detail":"..."}
    """
    image_model = body.image_model or _required("IMAGE_MODEL")
    try:
        full_prompt = build_full_prompt(style_id=body.style, user_prompt=body.prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    log.info(
        "generate model=%s batch=%d style=%s %dx%d seed=%s prompt=%r",
        image_model, body.batch_count, body.style, body.width, body.height,
        body.seed, body.prompt,
    )

    def gen() -> Iterator[str]:
        conn = db.connect()
        try:
            yield _ndjson({"type": "start", "batch_count": body.batch_count})
            for i in range(body.batch_count):
                seed_for_this = (
                    body.seed if body.seed is not None else secrets.randbelow(SEED_MAX)
                )
                yield _ndjson({"type": "image_start", "image_index": i, "seed": seed_for_this})

                final_result: ollama_client.GenerationResult | None = None
                try:
                    for ev in ollama_client.generate_image_streaming(
                        model=image_model,
                        prompt=full_prompt,
                        width=body.width,
                        height=body.height,
                        seed=seed_for_this,
                        negative_prompt=body.negative_prompt,
                        steps=body.steps,
                    ):
                        if isinstance(ev, ollama_client.ProgressEvent):
                            yield _ndjson({
                                "type": "progress",
                                "image_index": i,
                                "percent": ev.percent,
                                "step": ev.step,
                                "total": ev.total,
                            })
                        else:
                            final_result = ev
                except Exception as e:
                    log.exception("ollama generation failed")
                    yield _ndjson({"type": "error", "detail": str(e)})
                    return

                if final_result is None:
                    yield _ndjson({"type": "error", "detail": "no image produced"})
                    return

                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                # Record the actual number of steps the model ran (captured from
                # the progress events). Falls back to whatever the user requested
                # if we somehow didn't see any progress lines.
                actual_steps = final_result.steps_used or body.steps
                conn.execute(
                    """
                    INSERT INTO images (
                        id, filename, thumbnail, user_prompt, full_prompt,
                        negative_prompt, style, width, height, seed, steps,
                        model, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        final_result.image_id, final_result.filename, final_result.thumbnail,
                        body.prompt, full_prompt, body.negative_prompt, body.style,
                        body.width, body.height, seed_for_this, actual_steps,
                        image_model, now,
                    ),
                )
                image_out = ImageOut(
                    id=final_result.image_id,
                    filename=final_result.filename,
                    thumbnail=final_result.thumbnail,
                    user_prompt=body.prompt,
                    full_prompt=full_prompt,
                    negative_prompt=body.negative_prompt,
                    style=body.style,
                    width=body.width,
                    height=body.height,
                    seed=seed_for_this,
                    steps=actual_steps,
                    model=image_model,
                    created_at=now,
                )
                yield _ndjson({
                    "type": "image",
                    "image_index": i,
                    "image": image_out.model_dump(),
                })
            yield _ndjson({"type": "done"})
        finally:
            conn.close()

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/images", response_model=list[ImageOut])
def list_images(limit: int = 200) -> list[ImageOut]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM images ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [ImageOut(**dict(r)) for r in rows]


@app.get("/api/images/{image_id}")
def get_image_meta(image_id: str) -> ImageOut:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM images WHERE id = ?", (image_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return ImageOut(**dict(row))


def _serve_file(directory: Path, filename: str, download_name: str | None = None) -> FileResponse:
    p = directory / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="file missing on disk")
    if download_name:
        return FileResponse(p, media_type="image/png", filename=download_name)
    return FileResponse(p, media_type="image/png")


@app.get("/api/images/{image_id}/file")
def get_image_file(image_id: str, download: bool = False) -> FileResponse:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT filename, user_prompt FROM images WHERE id = ?", (image_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    name = None
    if download:
        # Make a friendly download name from the prompt, capped at 80 chars.
        slug = "".join(c if c.isalnum() or c in " -_" else "_" for c in row["user_prompt"])
        slug = slug.strip().replace(" ", "_")[:80] or "image"
        name = f"{slug}.png"
    return _serve_file(db.IMAGES_DIR, row["filename"], download_name=name)


@app.get("/api/images/{image_id}/thumb")
def get_image_thumb(image_id: str) -> FileResponse:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT thumbnail FROM images WHERE id = ?", (image_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return _serve_file(db.THUMBS_DIR, row["thumbnail"])


@app.delete("/api/images/{image_id}")
def delete_image(image_id: str) -> dict:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT filename, thumbnail FROM images WHERE id = ?", (image_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        for d, name in ((db.IMAGES_DIR, row["filename"]), (db.THUMBS_DIR, row["thumbnail"])):
            p = d / name
            if p.exists():
                p.unlink()
        conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
    finally:
        conn.close()
    return {"deleted": image_id}


def main() -> None:
    import uvicorn

    host = os.environ.get("IMAGE_SERVICE_HOST", "127.0.0.1")
    port = int(os.environ.get("IMAGE_SERVICE_PORT", "8765"))
    uvicorn.run("image_service.server:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
