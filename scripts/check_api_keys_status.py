import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv()

import requests
import jwt

API_BASE = "http://127.0.0.1:8000"
USER_ID = 2

secret = os.getenv("NEXTAUTH_SECRET")
db = None
try:
    from database import SessionLocal
    import models
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.id == USER_ID).first()
    email = user.email
except Exception as e:
    print(f"DB Error: {e}")
    email = "choiwangai@gmail.com"
finally:
    if db: db.close()

now = int(time.time())
token = jwt.encode(
    {"email": email, "sub": str(USER_ID), "iat": now, "exp": now + 3600},
    secret,
    algorithm="HS256",
)
if hasattr(token, "decode"):
    token = token.decode("utf-8")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 1. Check if user 2 has keys according to the running API
r = requests.get(f"{API_BASE}/api/keys", headers=headers)
print(f"GET /api/keys: status={r.status_code} body={r.text}")

# 2. Check /api/me to confirm it's working
r = requests.get(f"{API_BASE}/api/me", headers=headers)
print(f"GET /api/me: status={r.status_code} body={r.text}")
