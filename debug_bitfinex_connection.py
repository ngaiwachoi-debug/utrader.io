import hashlib
import hmac
import json
import time
import requests
import sys

# --- CONFIGURATION (Cursor will fill this) ---
API_KEY = "6088a8f93d6d811585827c8639e3541ff8cfd29589f"
API_SECRET = "7207e9ece87ac7550040c6d4a9446760484b71547ca"
# -------------------------------------------

BASE_URL = "https://api.bitfinex.com"

def test_endpoint(endpoint, payload={}):
    # 1. Nonce: Use microsecond timestamp for uniqueness
    nonce = str(int(time.time() * 1000000))
    
    # 2. Body: STRICT JSON serialization (No spaces allowed by Bitfinex)
    json_body = json.dumps(payload, separators=(',', ':'))

    # 3. Signature Payload: /api/ + path + nonce + body
    # Note: endpoint usually comes in as "v2/..." so we prepend "/api/"
    signature_payload = f"/api/{endpoint}{nonce}{json_body}"

    # 4. Sign it
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        signature_payload.encode('utf-8'),
        hashlib.sha384
    ).hexdigest()

    # 5. Headers
    headers = {
        'bfx-nonce': nonce,
        'bfx-apikey': API_KEY,
        'bfx-signature': signature,
        'content-type': 'application/json'
    }

    print(f"\n--- TESTING: {endpoint} ---")
    print(f"DEBUG: Payload Signed: '{signature_payload}'")
    
    try:
        response = requests.post(
            f"{BASE_URL}/{endpoint}",
            headers=headers,
            data=json_body # Send the EXACT string we signed
        )
        print(f"STATUS: {response.status_code}")
        print(f"RESPONSE: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    print(">>> STARTING RAW CONNECTION TEST")
    
    # TEST 1: User Info (Validates Keys)
    success = test_endpoint("v2/auth/r/info/user")
    
    if success:
        print("✅ CONNECTION SUCCESSFUL!")
        # TEST 2: Check Permissions (Validates Lending Access)
        test_endpoint("v2/auth/r/permissions")
    else:
        print("❌ CONNECTION FAILED. Check the Debug output above.")
