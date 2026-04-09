# Production deployment guide

This document describes how to run **Mastex SchoolOS** reliably in production: configuration, CI/CD, logging, monitoring, and backups.

## Architecture notes

- **Django 5** + **Gunicorn** + **WhiteNoise** for static assets  
- **PostgreSQL** in production (`DATABASE_URL` via `dj-database-url`)  
- Optional **Redis** for cache/sessions when `REDIS_URL` is set (otherwise database cache table)  
- **Sentry** for error tracking when `SENTRY_DSN` is set and `DEBUG=False`  
- **Docker** image defined in `Dockerfile`; health endpoint: `GET /health/`

---

## Environment variables

Copy `.env.example` to `.env` locally. On hosted platforms, set variables in the provider UI or secrets manager.

### Required for production

| Variable | Purpose |
|----------|---------|
| `DEBUG` | Must be `False` |
| `SECRET_KEY` | Strong random secret (never commit) |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `DATABASE_URL` | PostgreSQL connection URL |
| `CSRF_TRUSTED_ORIGINS` | `https://your-domain` (comma-separated) |

### Strongly recommended

| Variable | Purpose |
|----------|---------|
| `SENTRY_DSN` | Error and performance monitoring |
| `GIT_COMMIT_SHA` | Sentry release / deploy tracking |
| `SENTRY_ENVIRONMENT` | e.g. `production`, `staging` |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0`–`1.0` (default `0.1`) |
| `CORS_ALLOWED_ORIGINS` | Front-end origins for API (not `*` in prod) |
| `EMAIL_*` / `SENDGRID_API_KEY` | Outbound mail |
| `PAYSTACK_*` | Payments |
| `CRON_SECRET_KEY` | Protect scheduled job HTTP endpoints, if used |

### Logging

| Variable | Purpose |
|----------|---------|
| `LOG_LEVEL` | Root log level (`INFO`, `WARNING`, …) |
| `APP_LOG_LEVEL` | Overrides level for app loggers (`accounts`, `finance`, …) |
| `LOG_JSON` | `1` / `true` → JSON lines on stdout (for log aggregators) |

### Optional services

| Variable | Purpose |
|----------|---------|
| `REDIS_URL` | Cache + sessions |
| `SUPABASE_*` | Media / object storage integration |
| `MNOTIFY_*` | SMS |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | AI features |

### Docker-only

| Variable | Purpose |
|----------|---------|
| `DJANGO_SUPERUSER_PASSWORD` | Creates first superuser if none exists (remove after bootstrap) |
| `RUN_PREFLIGHT` | `1` → run `manage.py preflight` before Gunicorn (recommended for prod) |
| `PORT` | Listen port (default `8000`) |
| `WEB_CONCURRENCY` | Gunicorn workers (entrypoint sets a default if unset) |

---

## CI/CD

### GitHub Actions (included)

- **`.github/workflows/ci.yml`**  
  On push/PR to `main` or `master`: install deps, `check --deploy`, `makemigrations --check`, `migrate`, `collectstatic`, and **Docker build** (no push).

Add a test step when you introduce `pytest`:

```yaml
- run: pip install pytest pytest-django && pytest -q
```

### Deploy pipeline

1. Build and push the image to your registry (GHCR, ECR, GCR, Docker Hub).  
2. Deploy to **Railway**, **Render**, **Fly.io**, **Kubernetes**, etc.  
3. Set `GIT_COMMIT_SHA` to the deployed commit for Sentry releases.  
4. Run smoke checks: `GET /health/` returns `200` and `"database": "ok"`.

**`.github/workflows/deploy-template.yml`** is a stub for `workflow_dispatch`; replace with your platform’s deploy action or webhook.

### Platform hints

- **Railway**: `railway.json` defines health check and cron-style jobs. Set all env vars in the dashboard.  
- **Render**: `render.yaml` blueprint; set `DATABASE_URL`, `SECRET_KEY`, and hosts in the dashboard.  
- Use **pre-release environment** (staging) with a separate database and DSN.

---

## Logging

- **Console**: always; format is human-readable locally, optional **JSON** with `LOG_JSON=1` for centralized logging.  
- **File**: if `schoolms/logs/` is writable, warnings+ also go to rotating `app.log`.  
- **Errors**: `django.request` at `ERROR` can email **ADMINS** if SMTP is configured.

In Kubernetes / PaaS, prefer **stdout + JSON** and ship logs to your provider or **Loki / CloudWatch / Datadog**.

---

## Monitoring (Sentry)

When `SENTRY_DSN` is set and `DEBUG=False`:

- Django integration captures unhandled exceptions.  
- **LoggingIntegration** sends `ERROR` log records as Sentry events.  
- **Performance**: sampling via `SENTRY_TRACES_SAMPLE_RATE`; **profiles** via `SENTRY_PROFILES_SAMPLE_RATE`.  
- **`/health/`** is excluded from traces and error noise where possible.

**Alerting**: In Sentry, create alerts for unresolved issues, spike in error rate, and (optional) performance regressions.

---

## Backups

### PostgreSQL (application database)

1. **Managed provider**: enable automated backups (Render, Railway, Supabase, RDS, etc.) and test restores quarterly.  
2. **Self-managed**: schedule `scripts/backup_postgres.sh` (requires `postgresql-client` / `pg_dump`):

   ```bash
   chmod +x scripts/backup_postgres.sh
   export DATABASE_URL="postgresql://..."
   BACKUP_DIR=/secure/backups RETENTION_DAYS=14 ./scripts/backup_postgres.sh
   ```

3. Store dumps in **encrypted object storage** (S3, GCS, Supabase Storage) with **versioning** and restricted IAM.

### Media files

- If using **local disk** (`MEDIA_ROOT`), replicate to object storage or mount a persistent volume and include it in backup scope.  
- If using **Supabase Storage** or S3, rely on provider backup/versioning and document bucket names in your runbook.

### Restore drill

Periodically restore a backup to a **scratch database** and run `migrate` to verify compatibility.

---

## Production checklist

- [ ] `DEBUG=False`, strong `SECRET_KEY`, correct `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`  
- [ ] `DATABASE_URL` points to production PostgreSQL  
- [ ] `collectstatic` runs in the image build or release phase (already in `docker-entrypoint.sh`)  
- [ ] Migrations run automatically on deploy (entrypoint / platform `preDeployCommand`)  
- [ ] `SENTRY_DSN` and `GIT_COMMIT_SHA` set  
- [ ] `RUN_PREFLIGHT=1` in Docker after env is stable  
- [ ] Remove or rotate `DJANGO_SUPERUSER_PASSWORD` after first admin exists  
- [ ] HTTPS termination and proxy headers (`SECURE_PROXY_SSL_HEADER` already set)  
- [ ] Backups enabled + restore tested  
- [ ] Cron jobs (`railway.json` jobs) documented and `CRON_SECRET_KEY` secured  

---

## Operations commands

```bash
python manage.py preflight          # Before/after deploy validation
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createcachetable   # If using DB cache without Redis
python manage.py clearsessions      # Weekly (already scheduled in railway.json example)
```

---

## Security reminder

- Never commit `.env` or database URLs with credentials.  
- Rotate any secret that may have been exposed (repos, tickets, chat logs).  
- Restrict Paystack, SendGrid, and Supabase keys with least privilege.
