# Production audit — Mastex SchoolOS

**Purpose:** Single checklist of gaps, risks, and remediation toward a stable, issue-minimized release.  
**Not a guarantee of “zero bugs”** — it is the baseline for ongoing QA.

---

## Critical issues (fixed in repo)

| Item | Risk | Resolution |
|------|------|------------|
| JWT `BLACKLIST_AFTER_ROTATION=True` without blacklist app | Refresh-token rotation can **500** or leave invalid state | Added `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS`. **Run `migrate` on every environment.** |
| `chat_page` in `academics/timetable_generator.py` used `Student.assigned_subjects` (does not exist) | **FieldError** if route is ever used | Scoped teachers/parents via `teacher_student_scope` + `Timetable` (aligned with dashboard logic). |

---

## High priority (do next)

| Area | Gap | Action |
|------|-----|--------|
| Automated tests | No `pytest` / `TestCase` suite in repo | Add tests for: auth, school isolation, fee payment math, Paystack webhook, JWT refresh |
| Duplicate / dead routes | `timetable_generator.send_message` vs `messaging.send_message`; `chat_page` may be unused | Map URLs; remove or consolidate under `messaging` |
| Documentation drift | README mentions Flutterwave / OpenAI; product uses Paystack / Groq–Gemini | Align README and marketing with actual integrations |
| Secrets in chat/logs | `.env` must never be committed; rotate if leaked | Use `.env.example` only in git; secrets in host vault |

---

## Medium priority

| Area | Gap | Action |
|------|-----|--------|
| CORS | Production `CORS_ALLOWED_ORIGINS` empty breaks SPA clients | Set explicit origins per environment |
| Parent portal | Depth vs staff features | UX pass: fees, results, attendance, messaging on mobile |
| Migrations on deploy | Must succeed before traffic | Keep `migrate` in entrypoint; monitor failures |
| Backup drill | Restores untested = no backup | Quarterly restore to scratch DB |
| Sentry noise | Health checks / bots | Already sampled / filtered in settings; tune alerts in Sentry UI |

---

## Lower priority / hygiene

| Area | Note |
|------|------|
| `django-csp` | CSP headers partially via settings variables — confirm middleware if package used |
| Rate limits | DRF throttles present — review per endpoint for auth brute-force |
| i18n / a11y | Expand for tenders and inclusion |
| Performance | N+1 audits on heavy list views |

---

## Release gate (suggested)

- [ ] `python manage.py check --deploy` (production env vars)
- [ ] `python manage.py migrate --noinput`
- [ ] `python manage.py preflight` (optional `RUN_PREFLIGHT=1` in Docker)
- [ ] Smoke: `/health/`, login, one fee flow, one API token refresh
- [ ] CI green (`.github/workflows/ci.yml`)

---

## Sign-off

**“Issue-free”** for a live ERP means **controlled risk**: tests, monitoring, backups, and runbooks — not absence of all defects. Use this file as the living audit; update when you close items.

*Last updated: audit pass with JWT blacklist + chat scope fixes.*
