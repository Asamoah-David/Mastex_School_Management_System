# Mastex — Performance & Scalability Report

**Date:** 2026-05-06  
**Scope:** Django monolith (`schoolms/`), PostgreSQL/SQLite, Redis optional, Celery optional.

## Current optimisations

| Area | Mechanism |
|------|-----------|
| HTTP | `GZipMiddleware`, DRF pagination (`PAGE_SIZE=50`), JSON-only renderers in production |
| Static | WhiteNoise compressed manifest |
| Cache | Per-school term/grade boundary caching; dashboard cache in accounts |
| Database | Composite indexes on students, fee payments, results, report-card scores, early-warning flags |
| OMR | Validation before save; optional minimal debug PNGs; scheduled temp/debug pruning |
| Media | Optional JPEG resize/recompress (`core/media_utils`, env-tuned) |

## Recommended scaling path

1. **Application tier:** Run multiple Gunicorn/uvicorn workers behind a load balancer; sticky sessions not required for API JWT.
2. **Database:** PostgreSQL with connection pooling (PgBouncer). Add partial indexes for `students.status='active'` when row counts exceed ~100k per school.
3. **Cache:** Enable `REDIS_URL` for cross-worker cache and Celery broker.
4. **Celery:** Move bulk PDF/ZIP, large CSV exports, and full-class scheme recomputation to tasks (`academics.recompute_assessment_scheme_task` pattern).
5. **Object storage:** S3-compatible storage for `MEDIA_ROOT`; pair with **bucket lifecycle rules** (OMR debug/temp are not fully pruned on object stores by `cleanup_omr_images`).
6. **Read replicas:** For national-scale reporting, route heavy read-only reports to a replica.

## Slow query monitoring

- Enable `log_min_duration_statement` on Postgres in staging.
- Use Django `DEBUG` sql logging only locally — never in production.

## Frontend (server-rendered)

- Prefer pagination on all staff list views; avoid `select_related`/`prefetch_related` omissions on hot pages.
- For future SPA/mobile shells: virtualised tables, route-based code splitting, skeleton states.

## Metrics to watch

- p95 latency on `/portal/`, fee payment webhook, OMR upload.
- Celery queue depth and task failure rate.
- Disk use under `media/omr/` when `ENABLE_DEBUG_OVERLAYS=true`.

---

*Technical debt:* systematic audit of N+1 queries per app; load test before regional rollout.
