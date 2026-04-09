#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Logical backup of PostgreSQL (DATABASE_URL or standard PG* variables).
# Schedule via cron, Kubernetes CronJob, or your host's job runner.
#
# Usage:
#   export DATABASE_URL="postgresql://..."
#   ./scripts/backup_postgres.sh
#
# Optional:
#   BACKUP_DIR=/var/backups/schoolms RETENTION_DAYS=14 ./scripts/backup_postgres.sh
# -----------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/pg}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

if command -v pg_dump >/dev/null 2>&1; then
  :
else
  echo "pg_dump not found. Install postgresql-client." >&2
  exit 1
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  OUT="$BACKUP_DIR/schoolms_${STAMP}.sql.gz"
  echo "Dumping via DATABASE_URL -> $OUT"
  pg_dump "$DATABASE_URL" --no-owner --format=plain | gzip -9 >"$OUT"
else
  : "${PGHOST:?Set PGHOST or DATABASE_URL}"
  : "${PGUSER:?Set PGUSER or DATABASE_URL}"
  : "${PGDATABASE:?Set PGDATABASE or DATABASE_URL}"
  OUT="$BACKUP_DIR/schoolms_${STAMP}.sql.gz"
  echo "Dumping $PGDATABASE @ $PGHOST -> $OUT"
  pg_dump --no-owner --format=plain | gzip -9 >"$OUT"
fi

echo "Pruning backups older than ${RETENTION_DAYS} days in $BACKUP_DIR"
find "$BACKUP_DIR" -type f -name 'schoolms_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete || true

echo "Done."
