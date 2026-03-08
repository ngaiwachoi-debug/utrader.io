"""
Check bot status for a user via API endpoint /user-status/{user_id}

Usage:
    python scripts/check_bot_status.py 2
    python scripts/check_bot_status.py 2 --admin
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def get_jwt_for_user(user_id: int):
    """Get JWT token for a user."""
    secret = os.getenv("NEXTAUTH_SECRET", "").strip()
    if not secret:
        raise RuntimeError("NEXTAUTH_SECRET not set in .env")
    
    import jwt
    from database import SessionLocal
    import models
    
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise RuntimeError(f"User {user_id} not found")
        
        now = int(time.time())
        token = jwt.encode(
            {"email": user.email or "", "sub": str(user.id), "iat": now, "exp": now + 3600},
            secret,
            algorithm="HS256",
        )
        if hasattr(token, "decode"):
            token = token.decode("utf-8")
        return token
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Check bot status for a user")
    parser.add_argument("user_id", type=int, nargs="?", default=2, help="User ID (default: 2)")
    parser.add_argument("--admin", action="store_true", help="Use ADMIN_TOKEN")
    parser.add_argument(
        "--api-base",
        default=os.getenv("API_BASE", "http://127.0.0.1:8000"),
        help="Backend base URL",
    )
    args = parser.parse_args()
    
    # Build headers
    if args.admin:
        token = os.getenv("ADMIN_TOKEN", "").strip()
        if not token:
            print("ERROR: ADMIN_TOKEN not set. Use --admin only if ADMIN_TOKEN is in .env")
            return 1
        headers = {"Authorization": f"Bearer {token}"}
    else:
        try:
            token = get_jwt_for_user(args.user_id)
            headers = {"Authorization": f"Bearer {token}"}
        except Exception as e:
            print(f"ERROR: {e}")
            return 1
    
    # Call API
    url = f"{args.api_base.rstrip('/')}/user-status/{args.user_id}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"ERROR: HTTP {r.status_code}")
            print(r.text[:500])
            return 1
        
        data = r.json()
        print(f"\n=== Bot Status for User {args.user_id} ===\n")
        print(f"Bot Status:        {data.get('bot_status', 'N/A')}")
        print(f"Bot Desired State: {data.get('bot_desired_state', 'N/A')}")
        print(f"Tokens Remaining:  {data.get('tokens_remaining', 'N/A')}")
        print(f"Plan Tier:         {data.get('plan_tier', 'N/A')}")
        print(f"Gross Profit USD:  {data.get('gross_profit_usd', 'N/A')}")
        
        if 'botStats' in data:
            stats = data['botStats']
            print(f"\nBot Stats:")
            print(f"  Active Orders:   {stats.get('active_orders', 'N/A')}")
            print(f"  Total Loaned:    {stats.get('total_loaned', 'N/A')}")
            print(f"  WAROC:           {stats.get('waroc', 'N/A')}")
        
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
