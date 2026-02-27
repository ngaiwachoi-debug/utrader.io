#!/usr/bin/env bash
# Test Upstash Redis connection (REDIS_URL from .env). No local Redis required.
# Usage: ./scripts/test_upstash_redis.sh

set -e
cd "$(dirname "$0")/.."
python scripts/test_upstash_redis.py
