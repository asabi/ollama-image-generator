#!/bin/bash
# Run the image-gen service locally on the Mac.
#
# Pre-flight, in order:
#   1. Verify the host environment (macOS, ollama CLI, node, uv, iTerm2)
#   2. Auto-install Python + frontend deps if their folders are missing
#   3. Load .env and verify the configured Ollama server is reachable
#   4. Pull IMAGE_MODEL and ENHANCE_MODEL if they're not already installed
# Then open one iTerm2 tab per service (backend, frontend).

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# --- 1. Environment doctor --------------------------------------------------
errors=()
warnings=()

# macOS — Ollama's image-gen flags are currently macOS-only beta
if [[ "$OSTYPE" != "darwin"* ]]; then
  errors+=("This app currently only runs on macOS. Ollama's experimental image-generation flags (--width/--height/--seed) are Mac-only beta as of writing.")
fi

# ollama CLI — used to pull models and (via subprocess) to generate
if ! command -v ollama >/dev/null 2>&1; then
  errors+=("'ollama' CLI is not installed. Install from https://ollama.com")
fi

# node + npm — frontend can't run without them
if ! command -v node >/dev/null 2>&1; then
  errors+=("'node' is not installed. The frontend can't run. Install via 'brew install node' or from https://nodejs.org/")
fi
if ! command -v npm >/dev/null 2>&1; then
  errors+=("'npm' is not installed (usually ships with node).")
fi

# uv — used for backend deps; warning because user could run with venv+pip manually
if ! command -v uv >/dev/null 2>&1; then
  warnings+=("'uv' is not installed. The backend tab will fail to start. Install via 'brew install uv' or 'curl -LsSf https://astral.sh/uv/install.sh | sh'. Without uv you'd need to manage the Python venv manually.")
fi

# iTerm2 — this script uses osascript to spawn its tabs
if [[ ! -d "/Applications/iTerm.app" && ! -d "$HOME/Applications/iTerm.app" ]]; then
  warnings+=("iTerm2 not found in /Applications. run_local.sh uses osascript to open iTerm2 tabs and will fail at the last step. Install from https://iterm2.com/ — or run the two services manually (see README).")
fi

if [[ ${#warnings[@]} -gt 0 ]]; then
  printf "\n"
  for w in "${warnings[@]}"; do
    echo "⚠  WARNING: $w" >&2
  done
fi
if [[ ${#errors[@]} -gt 0 ]]; then
  printf "\n"
  for e in "${errors[@]}"; do
    echo "✗  ERROR: $e" >&2
  done
  printf "\nFix the errors above and re-run.\n" >&2
  exit 1
fi
echo "✓ Environment looks good"

# --- 2. Install deps if their folders are missing ---------------------------
if [[ ! -d ".venv" ]]; then
  echo "Setting up Python deps (first run — this is one-time)..."
  uv sync
fi
if [[ ! -d "frontend/node_modules" ]]; then
  echo "Setting up frontend deps (first run — this is one-time)..."
  (cd frontend && npm install)
fi

# --- 3. Load .env -----------------------------------------------------------
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

echo ""
echo "Pre-flight check:"
echo "  OLLAMA_BASE_URL = $OLLAMA_BASE_URL"
echo "  IMAGE_MODEL     = $IMAGE_MODEL"
echo "  ENHANCE_MODEL   = $ENHANCE_MODEL"
echo ""

# --- 4. Verify Ollama is reachable ------------------------------------------
if ! curl -sSf -m 5 "$OLLAMA_BASE_URL/api/tags" >/dev/null; then
  echo "ERROR: cannot reach Ollama at $OLLAMA_BASE_URL" >&2
  echo "Run 'ollama serve' or fix OLLAMA_BASE_URL in .env" >&2
  exit 1
fi
echo "✓ Ollama is reachable"

# --- 5. Pull missing models -------------------------------------------------
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
  OLLAMA_HOST="$OLLAMA_HOST_FOR_PULL" ollama pull "$model"
  echo "✓ $model pulled"
}

ensure_model "$IMAGE_MODEL"
ensure_model "$ENHANCE_MODEL"
echo ""

# --- 6. Open iTerm2 tabs ----------------------------------------------------
BACKEND_HOST="${IMAGE_SERVICE_HOST:-127.0.0.1}"
BACKEND_PORT="${IMAGE_SERVICE_PORT:-8765}"
BACKEND_HEALTH="http://${BACKEND_HOST}:${BACKEND_PORT}/api/styles"

echo "Starting backend in iTerm2..."
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
end tell
APPLESCRIPT

# Poll the backend until it answers. 60s should cover cold-start + first-run
# venv provisioning. If it never comes up, we still spawn the frontend so the
# user can see the error in its own tab — they can then check the backend tab.
echo -n "Waiting for backend to be ready"
for i in $(seq 1 60); do
  if curl -sSf -m 1 "$BACKEND_HEALTH" >/dev/null 2>&1; then
    echo " ✓ ready (after ${i}s)"
    backend_ready=1
    break
  fi
  echo -n "."
  sleep 1
done
if [[ -z "${backend_ready:-}" ]]; then
  echo ""
  echo "⚠  Backend didn't respond on $BACKEND_HEALTH within 60s — starting frontend anyway." >&2
  echo "   Check the image-studio-backend tab for errors." >&2
fi

echo "Starting frontend in iTerm2..."
osascript <<APPLESCRIPT
tell application "iTerm2"
    activate
    tell current window
        set newTab to (create tab with default profile)
        tell current session of newTab
            set name to "image-studio-frontend"
            write text "cd '${PROJECT_DIR}/frontend' && npm run dev"
        end tell
    end tell
end tell
APPLESCRIPT

echo ""
echo "Open http://localhost:${FRONTEND_PORT:-5173} — both services should be ready."
