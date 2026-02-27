# Test Upstash Redis connection (REDIS_URL from .env). No local Redis required.
# Usage: .\scripts\test_upstash_redis.ps1

Set-Location $PSScriptRoot\..
python scripts/test_upstash_redis.py
