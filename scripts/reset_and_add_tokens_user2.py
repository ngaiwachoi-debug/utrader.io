"""Reset user 2 token balance and add 1000 tokens (10 USD bypass)."""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# 1) List columns
cur.execute("""
  SELECT column_name FROM information_schema.columns
  WHERE table_name = 'user_token_balance' ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("user_token_balance columns:", cols)

# 2) Reset: set tokens_remaining=0, last_gross_usd_used=0 (and purchased_tokens=0 if exists)
set_parts = []
params = []
if "tokens_remaining" in cols:
    set_parts.append("tokens_remaining = 0")
if "last_gross_usd_used" in cols:
    set_parts.append("last_gross_usd_used = 0")
if "purchased_tokens" in cols:
    set_parts.append("purchased_tokens = 0")
if not set_parts:
    print("No known columns to reset")
    sys.exit(1)
cur.execute(
    "UPDATE user_token_balance SET " + ", ".join(set_parts) + " WHERE user_id = 2"
)
conn.commit()
print("Reset user_id=2:", ", ".join(set_parts))

# 3) Add 1000 purchased tokens: 10 USD * 100 = 1000. purchased_tokens = 0 + 1000
if "purchased_tokens" in cols:
    cur.execute(
        "UPDATE user_token_balance SET purchased_tokens = COALESCE(purchased_tokens, 0) + 1000 WHERE user_id = 2"
    )
    conn.commit()
    print("Added 1000 to purchased_tokens (10 USD * 100)")
if "tokens_remaining" in cols:
    cur.execute(
        "UPDATE user_token_balance SET tokens_remaining = COALESCE(tokens_remaining, 0) + 1000 WHERE user_id = 2"
    )
    conn.commit()
    print("Added 1000 to tokens_remaining")

# 4) Verify
cur.execute("SELECT * FROM user_token_balance WHERE user_id = 2")
row = cur.fetchone()
if row:
    print("After: user_id=2 row:", dict(zip([d[0] for d in cur.description], row)))
cur.close()
conn.close()
print("Done.")
