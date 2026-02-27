#!/usr/bin/env bash
# Watchdog: ensure uTrader backend (and thus 09:40/10:15 schedulers) is running. Restart if down.
# Run in background or via cron every 1–5 min. Uses no new env vars; API_BASE from .env or default.
# Usage: ./scripts/deduction_watchdog.sh   or   * * * * * /path/to/scripts/deduction_watchdog.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[ -f .env ] && set -a && source .env 2>/dev/null && set +a
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
LOG="$ROOT/logs/deduction_watchdog.log"
mkdir -p "$(dirname "$LOG")"

if command -v curl >/dev/null 2>&1; then
  if curl -sf --max-time 5 "$API_BASE/openapi.json" -o /dev/null 2>/dev/null; then
    exit 0
  fi
else
  if python -c "
import urllib.request
import os
url = os.environ.get('API_BASE', 'http://127.0.0.1:8000') + '/openapi.json'
try:
    urllib.request.urlopen(url, timeout=5)
except Exception:
    exit(1)
" 2>/dev/null; then
    exit 0
  fi
fi

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") backend not reachable, starting uvicorn" >> "$LOG"
cd "$ROOT"
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 >> "$LOG" 2>&1 &
echo $! >> "$ROOT/.utrader_uvicorn.pid"
