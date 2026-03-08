"""
Live-tail terminal logs for one user from the backend API.

Usage:
  python scripts/tail_terminal_logs.py --user-id 2
  python scripts/tail_terminal_logs.py --user-id 2 --interval 1.5 --admin

Auth:
  - If --admin is set, uses ADMIN_TOKEN and calls /admin/bot/logs/{user_id}
  - Otherwise uses NEXTAUTH_SECRET to mint a user JWT and calls /terminal-logs/{user_id}
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parent.parent
        load_dotenv(root / ".env")
    except Exception:
        pass


def _build_headers(user_id: int, admin: bool) -> dict:
    if admin:
        token = (os.getenv("ADMIN_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("ADMIN_TOKEN is required with --admin.")
        return {"Authorization": f"Bearer {token}"}

    secret = (os.getenv("NEXTAUTH_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("NEXTAUTH_SECRET is required (or use --admin with ADMIN_TOKEN).")

    import jwt

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise RuntimeError(f"User {user_id} not found.")
        now = int(time.time())
        token = jwt.encode(
            {"email": user.email or "", "sub": str(user.id), "iat": now, "exp": now + 3600},
            secret,
            algorithm="HS256",
        )
        if hasattr(token, "decode"):
            token = token.decode("utf-8")
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def _endpoint(base_url: str, user_id: int, admin: bool) -> str:
    if admin:
        return f"{base_url}/admin/bot/logs/{user_id}"
    return f"{base_url}/terminal-logs/{user_id}"


def main() -> int:
    _load_env()

    parser = argparse.ArgumentParser(description="Tail live bot terminal logs for a user.")
    parser.add_argument("--user-id", type=int, default=2, help="User ID to tail (default: 2)")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    parser.add_argument("--admin", action="store_true", help="Use ADMIN_TOKEN and admin endpoint")
    parser.add_argument(
        "--api-base",
        default=os.getenv("API_BASE", "http://127.0.0.1:8000"),
        help="Backend base URL (default: API_BASE env or http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    try:
        headers = _build_headers(args.user_id, args.admin)
    except Exception as e:
        print(f"[tail] auth setup failed: {e}")
        return 1

    url = _endpoint(args.api_base.rstrip("/"), args.user_id, args.admin)
    print(f"[tail] user_id={args.user_id} endpoint={url} interval={args.interval}s")
    print("[tail] Press Ctrl+C to stop.")

    seen_lines = []
    try:
        while True:
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code != 200:
                    print(f"[tail] HTTP {res.status_code}: {res.text[:200]}")
                    time.sleep(args.interval)
                    continue
                payload = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                lines = payload.get("lines") or []
                
                # Compare to find new lines even if list was truncated from start
                if not seen_lines:
                    new_lines = lines
                else:
                    # Find overlap
                    new_lines = []
                    last_seen = seen_lines[-1] if seen_lines else None
                    if last_seen in lines:
                        idx = lines.index(last_seen)
                        new_lines = lines[idx+1:]
                    else:
                        new_lines = lines
                
                if new_lines:
                    for line in new_lines:
                        try:
                            print(line)
                        except UnicodeEncodeError:
                            print(str(line).encode("ascii", errors="replace").decode("ascii"))
                
                seen_lines = lines
            except Exception as e:
                print(f"[tail] request error: {e}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[tail] stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

