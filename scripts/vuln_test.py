import requests, json, time
BASE = "http://127.0.0.1:8001"
results = []
PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

def test(name, status, detail=""):
    results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

print("=" * 70)
print("VULNERABILITY TEST SUITE")
print("=" * 70)

print("\n--- 1. Authentication Bypass Tests ---")
r = requests.get(f"{BASE}/bot-stats/2", timeout=5)
test("No token -> 401", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/bot-stats/2", headers={"Authorization": "Bearer invalidtoken"}, timeout=5)
test("Invalid token -> 401", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/bot-stats/2", headers={"Authorization": "invalid"}, timeout=5)
test("Malformed auth header -> 401", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/bot-stats/2", headers={"Authorization": "Bearer "}, timeout=5)
test("Empty bearer -> 401", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/bot-stats/2", headers={"Authorization": "Bearer ' OR 1=1 --"}, timeout=5)
test("SQLi in token -> 401", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")

print("\n--- 2. IDOR Tests ---")
r = requests.get(f"{BASE}/stats/1", timeout=5)
test("/stats/1 no auth", FAIL if r.status_code == 200 else PASS, f"status={r.status_code}")
r = requests.get(f"{BASE}/stats/2", timeout=5)
test("/stats/2 no auth", FAIL if r.status_code == 200 else PASS, f"status={r.status_code}")
r = requests.get(f"{BASE}/stats/1/history", timeout=5)
test("/stats/1/history no auth", FAIL if r.status_code == 200 else PASS, f"status={r.status_code}")
r = requests.get(f"{BASE}/stats/1/lending", timeout=10)
test("/stats/1/lending no auth", FAIL if r.status_code == 200 else PASS, f"status={r.status_code}")
r = requests.get(f"{BASE}/user-token-balance/1", timeout=5)
test("/user-token-balance/1 no auth", FAIL if r.status_code == 200 else PASS, f"status={r.status_code}")
r = requests.get(f"{BASE}/user-token-balance/2", timeout=5)
test("/user-token-balance/2 no auth", FAIL if r.status_code == 200 else PASS, f"status={r.status_code}")

print("\n--- 3. Admin Access Tests ---")
r = requests.get(f"{BASE}/admin/users", timeout=5)
test("GET /admin/users no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/admin/health", timeout=5)
test("GET /admin/health no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/admin/settings", timeout=5)
test("GET /admin/settings no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.post(f"{BASE}/admin/bot/start/2", timeout=5)
test("POST /admin/bot/start no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")

print("\n--- 4. Dev Endpoint Tests ---")
r = requests.post(f"{BASE}/dev/login-as", json={"email": "test@gmail.com"}, timeout=5)
test("/dev/login-as", PASS if r.status_code in (404, 403) else WARN, f"status={r.status_code}")
r = requests.post(f"{BASE}/dev/create-test-user", json={"email": "hacker@gmail.com"}, timeout=5)
test("/dev/create-test-user", PASS if r.status_code in (404, 403) else WARN, f"status={r.status_code}")
r = requests.post(f"{BASE}/dev/jwt-for-user", json={"user_id": 1}, timeout=5)
test("/dev/jwt-for-user", PASS if r.status_code in (404, 403) else WARN, f"status={r.status_code}")

print("\n--- 5. Bot Actions No Auth ---")
r = requests.post(f"{BASE}/start-bot", timeout=5)
test("POST /start-bot no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.post(f"{BASE}/stop-bot", timeout=5)
test("POST /stop-bot no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")

print("\n--- 6. Sensitive Data No Auth ---")
r = requests.get(f"{BASE}/wallets/2", timeout=5)
test("GET /wallets/2 no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/terminal-logs/2", timeout=5)
test("GET /terminal-logs/2 no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/user-status/2", timeout=5)
test("GET /user-status/2 no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/api/dashboard-fold", timeout=5)
test("GET /api/dashboard-fold no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/notifications", timeout=5)
test("GET /notifications no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")

print("\n--- 7. API Key Endpoints ---")
r = requests.post(f"{BASE}/connect-exchange", json={"bfx_key": "test", "bfx_secret": "test"}, timeout=5)
test("POST /connect-exchange no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")
r = requests.post(f"{BASE}/api/keys", json={"bfx_key": "test", "bfx_secret": "test"}, timeout=5)
test("POST /api/keys no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")

print("\n--- 8. Payment Endpoints ---")
r = requests.post(f"{BASE}/api/v1/tokens/deposit", json={"amount": 1000}, timeout=5)
test("POST /tokens/deposit no auth", PASS if r.status_code in (401, 404) else FAIL, f"status={r.status_code}")
r = requests.get(f"{BASE}/api/v1/users/me/token-balance", timeout=5)
test("GET /token-balance no auth", PASS if r.status_code == 401 else FAIL, f"status={r.status_code}")

print("\n--- 9. CORS ---")
r = requests.options(f"{BASE}/api/version", headers={"Origin": "http://evil-site.com", "Access-Control-Request-Method": "GET"}, timeout=5)
ao = r.headers.get("access-control-allow-origin", "")
test("CORS blocks evil origin", PASS if "evil-site.com" not in ao else FAIL, f"allow-origin={ao}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
warned = sum(1 for _, s, _ in results if s == WARN)
print(f"Total: {len(results)} | PASS: {passed} | FAIL: {failed} | WARN: {warned}")
if failed > 0:
    print("\nFAILED TESTS (CRITICAL):")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  ** {name}: {detail}")
if warned > 0:
    print("\nWARNINGS:")
    for name, status, detail in results:
        if status == WARN:
            print(f"  ?? {name}: {detail}")
print("=" * 70)