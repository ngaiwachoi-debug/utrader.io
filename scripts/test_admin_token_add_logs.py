"""
Test admin token-add logs: get admin user JWT and call GET /admin/token-add/logs.
Run from project root with backend up and ALLOW_DEV_CONNECT=1:
  python scripts/test_admin_token_add_logs.py
"""
import os
import sys

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    import requests
    from database import SessionLocal
    from models import User

    base = os.getenv("API_BASE", "http://127.0.0.1:8000")
    admin_email = os.getenv("ADMIN_EMAIL", "ngaiwachoi@gmail.com").strip().lower()

    # 1) Get admin user id from DB
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email.ilike(admin_email)).first()
        if not admin:
            print(f"Admin user not found for email={admin_email!r}")
            return 1
        admin_id = admin.id
        print(f"Admin user_id={admin_id} email={admin.email}")
    finally:
        db.close()

    # 2) Get JWT (dev endpoint)
    r = requests.post(f"{base}/dev/jwt-for-user", json={"user_id": admin_id}, timeout=10)
    if r.status_code != 200:
        print(f"JWT failed: {r.status_code} {r.text}")
        return 1
    token = r.json().get("token")
    if not token:
        print("No token in response")
        return 1
    print("Got JWT")

    # 3) Call admin token-add logs
    r2 = requests.get(
        f"{base}/admin/token-add/logs",
        params={"limit": 100},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print(f"GET /admin/token-add/logs -> {r2.status_code}")
    if r2.status_code != 200:
        print(r2.text)
        return 1
    data = r2.json()
    if not isinstance(data, list):
        print(f"Unexpected response: {type(data)}")
        return 1
    print(f"Entries returned: {len(data)}")
    for i, e in enumerate(data[:5]):
        print(f"  [{i}] user_id={e.get('user_id')} email={e.get('email')} amount={e.get('amount')} reason={e.get('reason')} detail={e.get('detail')}")
    if len(data) > 5:
        print(f"  ... and {len(data) - 5} more")
    return 0

if __name__ == "__main__":
    sys.exit(main())
