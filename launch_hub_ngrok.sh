#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-3031}"
CONFIG="${2:-hub_config.json}"
HOST="${HUB_HOST:-127.0.0.1}"
KILL_EXISTING="${HUB_KILL_EXISTING:-0}"

cd "$(dirname "$0")"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: config not found: $CONFIG" >&2
  exit 2
fi
if ! command -v ngrok >/dev/null 2>&1; then
  echo "ERROR: ngrok not found in PATH" >&2
  exit 2
fi

PID="$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN -n -P 2>/dev/null | head -n1 || true)"
if [[ -n "$PID" ]]; then
  if [[ "$KILL_EXISTING" == "1" ]]; then
    kill "$PID" >/dev/null 2>&1 || true
    sleep 1
  else
    echo "ERROR: port $PORT already in use by pid=$PID" >&2
    echo "Hint: HUB_KILL_EXISTING=1 ./launch_hub_ngrok.sh $PORT $CONFIG" >&2
    exit 1
  fi
fi

cleanup() {
  [[ -n "${HUB_PID:-}" ]] && kill "$HUB_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

python hub_server.py --host "$HOST" --port "$PORT" --config "$CONFIG" &
HUB_PID=$!
sleep 1
kill -0 "$HUB_PID" >/dev/null 2>&1 || { echo "ERROR: hub failed to start" >&2; exit 1; }

ngrok http "$PORT"
