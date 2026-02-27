"""
Run the ARQ worker (bot jobs, terminal logs). Uses REDIS_URL from .env — migrated to NEW Upstash server.
No local Redis required; rediss:// only.

Usage (from project root):
  python scripts/run_worker.py
"""
import os
import subprocess
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)

# Load .env so REDIS_URL is set (NEW Upstash server)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Prefer UTF-8 on Windows so worker print/logs don't hit cp950 encoding errors
env = os.environ.copy()
if sys.platform == "win32":
    env.setdefault("PYTHONIOENCODING", "utf-8")

if __name__ == "__main__":
    redis_url = env.get("REDIS_URL", "")
    if redis_url.strip().lower().startswith("rediss://"):
        try:
            from urllib.parse import urlparse
            host = urlparse(redis_url).hostname or "Upstash"
            print("Starting ARQ worker (Redis: %s). Ctrl+C to stop." % host)
        except Exception:
            print("Starting ARQ worker (Upstash Redis). Ctrl+C to stop.")
    else:
        print("Starting ARQ worker (Ctrl+C to stop). Set REDIS_URL in .env for Upstash.")
    sys.exit(subprocess.call([sys.executable, "-m", "arq", "worker.WorkerSettings"], cwd=root, env=env))
