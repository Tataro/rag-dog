#!/usr/bin/env bash
# Pulls the two models rag-dog uses. Idempotent — Ollama skips already-present models.
set -euo pipefail

OLLAMA_HOST="${OLLAMA_BASE_URL:-http://localhost:11434}"

# Use the CLI if installed natively (faster, GPU), otherwise hit the HTTP API.
if command -v ollama >/dev/null 2>&1; then
  pull() { ollama pull "$1"; }
else
  pull() {
    echo "→ pulling $1 via API at $OLLAMA_HOST"
    curl -sS -X POST "$OLLAMA_HOST/api/pull" \
      -H 'content-type: application/json' \
      -d "{\"model\":\"$1\",\"stream\":false}" \
      | tail -n 1
  }
fi

pull bge-m3
pull qwen2.5:14b-instruct

echo "✓ models ready"
