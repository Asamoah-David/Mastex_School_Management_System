# Mastex — Security Report (summary)

**Date:** 2026-05-06

## Controls in place

- **Authentication:** Session + JWT; login throttling; optional 2FA (TOTP).
- **Authorisation:** Role helpers in `accounts/permissions.py`; feature flags `core/feature_access.py`.
- **Tenant isolation:** School FK on tenant models; API views scoped (results, timetable, transcripts, fees).
- **CSRF / XSS:** Django defaults; template escaping; DRF without Browsable API in production.
- **Uploads:** `core/upload_validation.py` for images; size limits via Django settings.
- **Audit:** `audit.AuditLog` append-only; GDPR export request model; fee void events logged.
- **Deploy gate:** `production_check` warns on `DEBUG`, weak secrets, in-memory Celery broker, open hosts.
- **Results integrity:** Workflow + lock model on `academics.Result`; `ScoreChangeLog` for field-level history.
- **Finance:** Payment void via `voided_at` + balance adjustment (no silent row delete in normal flow).

## Hardening checklist (production)

1. `DEBUG=False`, strong `SECRET_KEY`, explicit `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
2. `CELERY_BROKER_URL=redis://...` (not `memory://`).
3. HTTPS only; HSTS at reverse proxy.
4. `ENABLE_DEBUG_OVERLAYS=False` (default when `DEBUG=False`).
5. Restrict `/admin/` by IP or SSO where possible.
6. Sentry or equivalent (`sentry-sdk` in requirements) with PII scrubbing.
7. Regular dependency updates (`pip-audit` / Dependabot).

## Known residual risks

- **Bulk `QuerySet.update()`** bypasses model `save()` — no `ScoreChangeLog` for those paths; prefer documented admin procedures or switch to iterative saves for sensitive fields.
- **Media URLs:** Ensure private buckets or signed URLs for sensitive documents; OMR debug paths should not be world-readable in high-trust exam scenarios.
- **Permission matrix:** Per-school custom roles are not fully generalised; new views must call explicit predicates.

---

*For penetration-test scope, include multi-tenant IDOR fuzzing on all DRF list endpoints.*
