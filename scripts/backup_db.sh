#!/usr/bin/env bash
#
# Database backup script for uTrader/bifinexbot (Linux/macOS).
# Creates a timestamped pg_dump and rotates old backups.
#
# Usage:
#   bash scripts/backup_db.sh
#
# Crontab (daily at 04:00):
#   0 4 * * * cd /path/to/project && bash scripts/backup_db.sh >> backups/backup.log 2>&1

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env not found at $ENV_FILE"
    exit 1
fi

DATABASE_URL=$(grep -E '^\s*DATABASE_URL\s*=' "$ENV_FILE" | head -1 | sed 's/.*=\s*"\?\([^"]*\)"\?/\1/')
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not found in .env"
    exit 1
fi

BACKUP_DIR="$ROOT/backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/utrader_${TIMESTAMP}.sql.gz"

echo "Starting database backup..."
echo "  Target: $BACKUP_FILE"

pg_dump "$DATABASE_URL" --no-owner --no-acl | gzip > "$BACKUP_FILE"
SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "OK: Backup complete ($SIZE)"

# Rotate: keep last 30 backups
KEEP=30
COUNT=$(ls -1 "$BACKUP_DIR"/utrader_*.sql.gz 2>/dev/null | wc -l)
if [ "$COUNT" -gt "$KEEP" ]; then
    ls -1t "$BACKUP_DIR"/utrader_*.sql.gz | tail -n +"$((KEEP + 1))" | while read -r f; do
        rm -f "$f"
        echo "  Rotated: $(basename "$f")"
    done
fi

echo "Done. Backups in $BACKUP_DIR (keeping last $KEEP)."
