# Mastex — Backup & Recovery Guide

**Date:** 2026-05-06

## Database

### Command

`python manage.py backup_database`

- **SQLite:** File copy to `BACKUP_DIR` or `backups/`.
- **PostgreSQL:** `pg_dump` when `DATABASE_URL` points to Postgres.

### Scheduling

Run via cron or Celery periodic task at low-traffic hours. Store dumps off-server (encrypted object storage).

## Media

- Copy `MEDIA_ROOT` (or sync S3 bucket) — includes report card PDFs, OMR artefacts, uploads.
- After RPO targets, pair DB backup time with media snapshot time.

## Recovery

1. Restore DB from latest verified dump (test restores quarterly).
2. Restore media tree or re-point bucket.
3. Run `migrate` if code version moved forward.
4. **Celery:** Replay failed tasks from `core.AsyncJob` if used; clear poison messages from broker.
5. **Paystack:** Reconcile settlements after restore (`finance` reconciliation tools / admin actions).

## Verification

- After restore, run `production_check`, smoke login, and spot-check fee balances vs payment rows (including non-voided payments only).

## Disaster scenarios

| Scenario | Action |
|----------|--------|
| DB corruption | Promote latest good backup; accept RPO window |
| Accidental mass delete | Restore DB + media; void events are audit-logged |
| Region outage | Fail over app + DB replica; update DNS |

---

*Document RPO/RTO with your board; this file is technical, not legal.*
