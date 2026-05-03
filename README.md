# Local Image Studio

A small local web app that wraps Ollama's experimental image-generation models (e.g. `x/z-image-turbo`, `x/flux2-klein`) with a clean Vue 3 UI, plus AI-powered prompt enhancement (any installed text model — gemma, qwen, llama, etc.) and a persistent gallery.

Runs entirely on your own machine — no external services, no cloud calls.

## What it does

- **Style picker** — realistic / cartoon / anime / oil painting / watercolor / 3D render / pixel art / sketch / cinematic. The selected style always prepends keywords to the prompt sent to the model.
- **Prompt + optional negative prompt + batch count.**
- **Real width/height control** via Ollama's experimental image-gen flags (`ollama run --width --height ...`).
- **Seed control** — leave blank for a fresh random seed per image (recorded so you can reproduce it later), or lock a specific seed for deterministic regeneration.
- **"Enhance with AI"** — sends your idea + style hint to whichever text model you pick on the local Ollama and replaces the prompt with a richer version. The dropdown lists every installed text model (anything advertising the `completion` capability via `/api/show` — gemma, qwen, llama, glm, etc.).
- **Dynamic model discovery** — image and text models are detected via Ollama's `/api/show` capabilities, so any new image-gen model you pull shows up automatically. A small catalog of well-known names (z-image-turbo variants, flux2-klein variants, popular text models) appears in the dropdowns even if you haven't pulled them — selecting one reveals an inline "Pull it now" button with a real progress bar.
- **Live progress streaming** for both flows:
  - Enhance streams the text model's tokens into the prompt textarea as they're generated.
  - Generate streams a real progress bar `Image 1 of 3 — 67% (6/9 steps)` parsed from `ollama run`'s stderr; each completed image flies into the gallery as it finishes.
- **Gallery** with thumbnails. Click a thumbnail → modal with full image, metadata (style, size, seed, full prompt sent), download button, "Reuse prompt" button (loads everything — including the seed — back into the form), delete button (with confirm modal).
- **All metadata persists** in SQLite (`image_service/data/images.db`). PNGs live in `image_service/data/images/`, thumbnails in `image_service/data/thumbs/`.

## Prerequisites

- macOS with iTerm2 (only needed if you use `run_local.sh`; otherwise the two services can be started any way you like).
- [Ollama](https://ollama.com) running locally on `http://localhost:11434` with these models pulled:
  - An image-gen model — e.g. `ollama pull x/z-image-turbo` or `ollama pull x/flux2-klein`
  - At least one text model for prompt enhancement — e.g. `ollama pull gemma4:31b`, `ollama pull qwen3:30b`, `ollama pull llama3.3` (anything that advertises the `completion` capability works)
- Python 3.12+ managed via [uv](https://github.com/astral-sh/uv).
- Node 20+ for the frontend.

## Setup

```bash
# 1. Backend deps
uv sync

# 2. Frontend deps
cd frontend && npm install && cd ..

# 3. Environment
cp .env.example .env
# edit .env if you want to change ports or pick a different default text model
```

## Run

```bash
./run_local.sh
```

Opens two iTerm2 tabs:
- `image-studio-backend` → FastAPI on `http://127.0.0.1:8765` (configurable via `IMAGE_SERVICE_PORT`)
- `image-studio-frontend` → Vite on `http://localhost:5173` (configurable via `FRONTEND_PORT`)

Open http://localhost:5173 in a browser.

Or run them individually:

```bash
# backend
uv run python -m image_service.server

# frontend
cd frontend && npm run dev
```

VS Code launch configs for both are in [.vscode/launch.json](.vscode/launch.json).

## API

Backend lives at `http://127.0.0.1:8765` by default. The Vite dev server proxies `/api/*` to it, so the frontend just calls `/api/...` directly.

| Method | Path                        | Purpose                                                                    |
|--------|-----------------------------|----------------------------------------------------------------------------|
| GET    | `/api/styles`               | List available styles                                                      |
| GET    | `/api/models`               | Lists installed image + text models, plus catalog entries that can be pulled |
| POST   | `/api/pull`                 | Stream Ollama's pull progress for a model (NDJSON: status / digest / total / completed) |
| POST   | `/api/enhance`              | Stream `chunk` / `final` events as the text model writes the enhanced prompt |
| POST   | `/api/generate`             | Stream `start` / `image_start` / `progress` / `image` / `done` events      |
| GET    | `/api/images`               | Newest-first list of all generations                                       |
| GET    | `/api/images/{id}`          | Metadata for one image                                                     |
| GET    | `/api/images/{id}/file`     | Full PNG (`?download=true` adds a friendly filename)                       |
| GET    | `/api/images/{id}/thumb`    | 320px thumbnail                                                            |
| DELETE | `/api/images/{id}`          | Remove from disk and DB                                                    |

Both streaming endpoints return `application/x-ndjson` (one JSON object per line). The frontend reads them via `fetch + ReadableStream` ([frontend/src/api.js](frontend/src/api.js)).

## Generation parameters

The backend invokes ollama with its experimental image-gen flags:

```
ollama run --width W --height H --seed S [--negative "..."] [--steps N] MODEL "<prompt>"
```

If `seed` is not provided, the backend picks a random one and records it on the row so you can reproduce later. If `steps` is not provided, ollama uses the model's recommended default.

## Env vars

See [.env.example](.env.example). The backend fails loudly on startup if any required var is missing — no silent defaults.

## Known limitations

- **No queue / concurrency** — `POST /api/generate` is synchronous and runs ollama inline. Long prompts block the request. Fine for single-user local use; would need a worker queue for anything bigger.
- **Image-gen flags are experimental** — they're listed under "Image Generation Flags (experimental)" in `ollama run --help`, so the names could change in a future Ollama version.

## Project layout

```
.
├── image_service/
│   ├── server.py            # FastAPI app (entry point)
│   ├── db.py                # SQLite + auto migrations
│   ├── ollama_client.py     # `ollama run` subprocess + streaming progress parser
│   ├── enhance.py           # text-model prompt enhancement via LiteLLM (streaming)
│   ├── models.py            # /api/show capability discovery + curated pull catalog
│   ├── styles.py            # style templates
│   ├── migrations/*.sql     # tracked schema migrations
│   └── data/                # gitignored: images.db, images/, thumbs/
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.js
        ├── App.vue
        ├── api.js           # fetch + NDJSON stream helper
        ├── style.css
        └── components/
            ├── GenerateForm.vue
            ├── Gallery.vue
            └── ImageModal.vue
```

## License

MIT — see [LICENSE](LICENSE).
