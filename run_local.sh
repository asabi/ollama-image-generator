#!/bin/bash
# Run the image-gen service locally on the Mac.
#
# Pre-flight:
#   1. Load .env
#   2. Verify the configured Ollama server is reachable
#   3. Pull IMAGE_MODEL and ENHANCE_MODEL if they're not already installed
# Then open one iTerm2 tab per service (backend, frontend).

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# --- 1. Load .env -----------------------------------------------------------
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found in $PROJECT_DIR" >&2
  echo "Copy .env.example to .env and fill it in." >&2
  exit 1
fi
set -a
source .env
set +a

: "${OLLAMA_BASE_URL:?OLLAMA_BASE_URL not set in .env}"
: "${IMAGE_MODEL:?IMAGE_MODEL not set in .env}"
: "${ENHANCE_MODEL:?ENHANCE_MODEL not set in .env}"

echo "Pre-flight check:"
echo "  OLLAMA_BASE_URL = $OLLAMA_BASE_URL"
echo "  IMAGE_MODEL     = $IMAGE_MODEL"
echo "  ENHANCE_MODEL   = $ENHANCE_MODEL"
echo ""

# --- 2. Verify Ollama is reachable ------------------------------------------
if ! curl -sSf -m 5 "$OLLAMA_BASE_URL/api/tags" >/dev/null; then
  echo "ERROR: cannot reach Ollama at $OLLAMA_BASE_URL" >&2
  echo "Run 'ollama serve' or fix OLLAMA_BASE_URL in .env" >&2
  exit 1
fi
echo "✓ Ollama is reachable"

# --- 3. Pull missing models -------------------------------------------------
INSTALLED_MODELS="$(
  curl -sS "$OLLAMA_BASE_URL/api/tags" \
    | grep -oE '"name":"[^"]+"' \
    | sed 's/"name":"\([^"]*\)"/\1/'
)"

# `ollama pull` reads OLLAMA_HOST in `host:port` form (no scheme, no trailing slash).
OLLAMA_HOST_FOR_PULL="${OLLAMA_BASE_URL#http://}"
OLLAMA_HOST_FOR_PULL="${OLLAMA_HOST_FOR_PULL#https://}"
OLLAMA_HOST_FOR_PULL="${OLLAMA_HOST_FOR_PULL%/}"

ensure_model() {
  local model="$1"
  if printf "%s\n" "$INSTALLED_MODELS" | grep -Fxq -- "$model"; then
    echo "✓ $model already installed"
    return
  fi
  echo "⤓ $model not found on $OLLAMA_BASE_URL — pulling now (this can take a while)..."
  if ! command -v ollama >/dev/null; then
    echo "ERROR: 'ollama' CLI is not installed locally; cannot pull." >&2
    echo "Install Ollama from https://ollama.com or pull the model manually." >&2
    exit 1
  fi
  OLLAMA_HOST="$OLLAMA_HOST_FOR_PULL" ollama pull "$model"
  echo "✓ $model pulled"
}

ensure_model "$IMAGE_MODEL"
ensure_model "$ENHANCE_MODEL"
echo ""

# --- 4. Open iTerm2 tabs ----------------------------------------------------
echo "Starting backend + frontend in iTerm2..."

osascript <<APPLESCRIPT
tell application "iTerm2"
    activate

    tell current window
        set newTab to (create tab with default profile)
        tell current session of newTab
            set name to "image-studio-backend"
            write text "cd '${PROJECT_DIR}' && uv run python -m image_service.server"
        end tell
    end tell

    tell current window
        set newTab to (create tab with default profile)
        tell current session of newTab
            set name to "image-studio-frontend"
            write text "cd '${PROJECT_DIR}/frontend' && npm run dev"
        end tell
    end tell
end tell
APPLESCRIPT

echo "Open http://localhost:${FRONTEND_PORT:-5173} once both tabs are ready."
