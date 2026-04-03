#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo ".env not found at $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

KEY="${DASHSCOPE_API_KEY:-}"
URL="${LLM_BASE_URL:-${DASHSCOPE_BASE_URL:-${OPENAI_BASE_URL:-}}}"
MODEL="${LLM_MODEL:-qwen3-max}"

if [[ -z "$KEY" ]]; then
  echo "DASHSCOPE_API_KEY is empty" >&2
  exit 1
fi

if [[ -z "$URL" ]]; then
  echo "No LLM base URL found. Expected LLM_BASE_URL, DASHSCOPE_BASE_URL, or OPENAI_BASE_URL." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
HEADERS_FILE="$TMP_DIR/headers.txt"
BODY_FILE="$TMP_DIR/body.txt"
trap 'rm -rf "$TMP_DIR"' EXIT

read -r -d '' REQUEST_BODY <<EOF || true
{
  "model": "$MODEL",
  "messages": [
    {"role": "user", "content": "Reply with OK only."}
  ],
  "temperature": 0.1
}
EOF

echo "Repo root: $REPO_ROOT"
echo "URL: $URL"
echo "MODEL: $MODEL"
echo "KEY prefix: ${KEY:0:8}"
echo

HTTP_CODE="$(
  curl -sS \
    -D "$HEADERS_FILE" \
    -o "$BODY_FILE" \
    -w '%{http_code}' \
    "$URL" \
    -H "Authorization: Bearer $KEY" \
    -H 'Content-Type: application/json' \
    --data "$REQUEST_BODY"
)"

echo "=== HTTP STATUS ==="
echo "$HTTP_CODE"
echo

echo "=== RESPONSE HEADERS ==="
cat "$HEADERS_FILE"
echo

echo "=== RESPONSE BODY ==="
cat "$BODY_FILE"
echo
