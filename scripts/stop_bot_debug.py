#!/usr/bin/env python3
"""
Debug script for Stop Bot failures.

After clicking "Stop Bot" in the UI:
  1. Backend logs: check the terminal where uvicorn runs for lines like
     stop_bot ENTRY user_id=... / stop_bot EXIT ... / stop_bot ... failed
  2. Frontend logs: open browser DevTools (F12) -> Console, filter by "[stop-bot]"
  3. This script: run `python scripts/stop_bot_debug.py` to print the last
     stop_bot_debug.log entries (written by the backend on each stop-bot call).

Usage:
  python scripts/stop_bot_debug.py           # show last N lines of stop_bot_debug.log
  python scripts/stop_bot_debug.py --tail 50  # show last 50 lines
  python scripts/stop_bot_debug.py --clear    # truncate log (start fresh)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, "stop_bot_debug.log")


def main():
    import argparse
    p = argparse.ArgumentParser(description="Inspect stop_bot_debug.log written by the backend")
    p.add_argument("--tail", type=int, default=20, help="Show last N lines (default 20)")
    p.add_argument("--clear", action="store_true", help="Truncate the log file")
    args = p.parse_args()

    if args.clear:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("")
            print("Cleared", LOG_PATH)
        else:
            print("Log file does not exist:", LOG_PATH)
        return

    if not os.path.exists(LOG_PATH):
        print("Log file not found:", LOG_PATH)
        print("Click Stop Bot in the UI once, then run this script again (backend must be running).")
        return 1

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    n = min(args.tail, len(lines))
    if n == 0:
        print("Log file is empty.")
        return 0

    print(f"Last {n} line(s) of {LOG_PATH}:\n")
    for line in lines[-n:]:
        print(line, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
