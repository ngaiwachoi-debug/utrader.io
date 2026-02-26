"""
Run the ARQ worker so queued bot jobs execute and the Trading Terminal shows output.
Requires: Redis running (e.g. redis-server or Upstash REDIS_URL in .env).

Usage (from project root):
  python scripts/run_worker.py
"""
import os
import subprocess
import sys

# Prefer UTF-8 on Windows so worker print/logs don't hit cp950 encoding errors
env = os.environ.copy()
if sys.platform == "win32":
    env.setdefault("PYTHONIOENCODING", "utf-8")

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)

if __name__ == "__main__":
    print("Starting ARQ worker (Ctrl+C to stop). Ensure Redis is running.")
    sys.exit(subprocess.call([sys.executable, "-m", "arq", "worker.WorkerSettings"], cwd=root, env=env))
