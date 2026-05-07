# Mastex — Deployment Guide

**Date:** 2026-05-06

## Quick start (production-shaped)

1. **Environment**
   - `DATABASE_URL` (PostgreSQL recommended)
   - `SECRET_KEY`, `DEBUG=False`
   - `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
   - `REDIS_URL` + `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
2. **Migrate & static**
   - `python manage.py migrate`
   - `python manage.py collectstatic --noinput`
3. **Processes**
   - Web: Gunicorn (or uvicorn for ASGI)
   - Worker: `celery -A schoolms.celery_app worker -l info`
   - Beat: `celery -A schoolms.celery_app beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler`
4. **Checks**
   - `python manage.py production_check`
   - `GET /health/` (DB + cache) and `GET /ready/` (fail if DB down)

## Platform notes

- **Railway / Render / Fly:** See `docs/RAILWAY_CHECKLIST.md`, `docs/GO_LIVE.md` for provider-specific env vars.
- **Media:** Mount persistent volume or use S3 backend; align `MEDIA_ROOT` / `STORAGES`.

## Enterprise env (this release)

```
KEEP_RAW_SCANS_DAYS=1
KEEP_DEBUG_OVERLAYS_DAYS=3
ENABLE_DEBUG_OVERLAYS=false
AUTO_CLEANUP_ENABLED=true
ENABLE_RAW_SCAN_STORAGE=true
```

## Post-deploy

- Create superuser; configure school subdomain and features.
- Verify Paystack webhooks against public URL.
- Smoke: staff login, fee payment, OMR upload, parent portal.

## Extended documentation

- `docs/DEPLOYMENT.md` — additional detail if present in repo.

---

*Rotate secrets on compromise; never commit `.env`.*
