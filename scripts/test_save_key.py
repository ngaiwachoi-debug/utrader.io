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
API_KEY = os.getenv("TEST_BFX_KEY", "")
API_SECRET = os.getenv("TEST_BFX_SECRET", "")
if not API_KEY or not API_SECRET:
    print("ERROR: Set TEST_BFX_KEY and TEST_BFX_SECRET env vars.")
    sys.exit(1)

secret = os.getenv("NEXTAUTH_SECRET")
db = None
from database import SessionLocal
import models
db = SessionLocal()
user = db.query(models.User).filter(models.User.id == USER_ID).first()
email = user.email

now = int(time.time())
token = jwt.encode(
    {"email": email, "sub": str(USER_ID), "iat": now, "exp": now + 3600},
    secret,
    algorithm="HS256",
)
if hasattr(token, "decode"):
    token = token.decode("utf-8")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

payload = {
    "bfx_key": API_KEY,
    "bfx_secret": API_SECRET
}

print("Saving keys...")
r = requests.post(f"{API_BASE}/connect-exchange", headers=headers, json=payload)
print(f"Status: {r.status_code}")
print(f"Body: {r.text}")

print("Checking vault...")
u = db.query(models.User).filter(models.User.id == USER_ID).first()
print("Vault saved:", bool(u.vault))
