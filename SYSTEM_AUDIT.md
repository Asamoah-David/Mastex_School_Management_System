# Mastex School Management System — System Audit

**Audit date:** 2026-05-05  
**Codebase:** Django 5.x monolith under `schoolms/`, server-rendered templates + DRF APIs where configured.

This document maps the product against the 25 audit areas, records **what already exists**, **gaps / risks**, and **changes applied in this audit pass**. It is a living document: extend it as you close gaps.

---

## Deliverables checklist

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Full audit report (this file) | Done |
| 2 | Bugs found and fixed | See [§ Bugs fixed](#bugs-fixed-this-pass) |
| 3 | Performance improvements | See [§ Performance](#1-performance) and improvements list |
| 4 | Database indexes added | See [§ Database indexes](#database-indexes-added-this-pass) |
| 5 | Security improvements | See [§ Security](#3-security) and improvements list |
| 6 | New / improved features | See [§ Features](#new-or-improved-features-this-pass) |
| 7 | Migration files | `students/0021_*`, `finance/0035_*` |
| 8 | Tests for critical features | `core/tests/test_upload_validation.py`, `integrations/tests/test_api_privacy.py` (+ OMR/academics) |
| 9 | Admin setup wizard | Partial / see [§ School setup](#8-school-setup-improvements) |
|10 | Optimized dashboards | Partial / see [§ Performance](#1-performance) |
|11 | Problem-solving modules | Many exist; see per-section gaps |

---

## Priority roadmap (from your spec)

1. **Security & permissions** — Harden endpoints, tenant isolation, upload validation, audit coverage.  
2. **Speed & database** — Indexes, pagination, caching, avoid full-table loads.  
3. **Report cards** — `SchemeBasedGradingService`, `StudentReportCardScore`; ensure traceability & tests.  
4. **Finance** — Soft-deleted fees excluded from dashboards where appropriate; payment indexes.  
5. **Attendance & communication** — Models/views exist; bulk queue & templates vary.  
6. **OMR** — Production pipeline + calibration; continue queue & storage cleanup.  
7. **Parent/student portal** — Fees, results, announcements; tighten scoping.  
8. **Setup wizard & UX** — Incremental wizard vs single forms.  
9. **Optional modules** — Inventory/library/transport/hostel when enabled.

---

## 1. Performance

### Current strengths

- **Dashboard caching:** `_cached_dashboard_data` / `DASHBOARD_CACHE_SECONDS` in `accounts/views.py`.  
- **DRF throttling** and pagination in settings (where APIs used).  
- **Health / readiness:** routes wired in `urls.py` (from earlier review).  
- **Celery:** `celery_app.py`, `CELERY_*` in `settings.py`, scheduled tasks in `core/tasks.py`.

### Gaps

- Many list views may still load large querysets without server-side pagination (audit per app).  
- Report card PDF / bulk CSV should run in Celery tasks for large schools.  
- Image compression for generic uploads (not only OMR temp files) is inconsistent.  
- Frontend: no React global error boundary in repo (server-rendered primary).

### Improvements this pass

- **Fee aggregates** on super-admin and school dashboards now **exclude soft-deleted fees** (`deleted_at__isnull=True`), so metrics match “active billing” reality and avoid overstating totals.  
- **Composite indexes** for common list/filter patterns (students by class/status; payments by school/time).  
- **OMR uploads:** validation before save reduces wasted CPU on bad files.

---

## 2. Database

### Current strengths

- **Tenancy helpers:** `SchoolScopedModel`, `SoftDeleteManager` in `core/tenancy.py`.  
- **Students:** soft delete, admission uniqueness, indexes on `(school, class_name)`, `(school, status)`.  
- **Fees:** indexes on `(school, student)`, `(school, paid)`, due dates, etc.  
- **Academics:** structured `Term`, `AssessmentScheme`, `StudentReportCardScore` for traceable scheme-based grading.

### Gaps

- Periodic review for **duplicate legacy fields** (e.g. fee `term` CharField vs `term_fk`).  
- **Partial indexes** (e.g. active-only students) worth adding on Postgres for huge datasets.  
- **Audit log** not automatically attached to every sensitive model (see §7).

### Indexes added this pass

See [Database indexes added](#database-indexes-added-this-pass).

---

## 3. Security

### Current strengths

- **Login rate limiting** (cache + IP via trusted resolver) and lockout fields on user (`accounts/views.py`).  
- **Permission helpers:** `accounts/permissions.py` (`user_can_manage_school`, `can_manage_finance`, etc.).  
- **Feature flags:** `core/feature_access.py` (`@feature_required`).  
- **RLS-related migrations** under `core/migrations` for Supabase posture.

### Gaps

- **Systematic review** of every DRF viewset / function view for `school` scoping and role checks (ongoing).  
- **JWT / API** abuse: align throttles with login limits for auth endpoints.  
- **File uploads** outside OMR (assignments, documents) need the same validation pattern as introduced for OMR.

### Improvements this pass

- **Centralized image upload validation** (`core/upload_validation.py`): extension allow-list, size limit (uses `OMR_MAX_UPLOAD_BYTES` or `DATA_UPLOAD_MAX_MEMORY_SIZE`), optional Pillow verify.  
- **OMR views** use validation on all temp saves and calibration blank sheets (invalid blank → warning, coordinates still saved).  
- **REST API privacy (2026 follow-up):** `ResultListAPIView` no longer exposes every published score to any logged-in school user; **teaching + leadership** see school-wide published results; **parents** see linked children only; **students** see self only; **librarian/accountant/etc.** receive 403. Same pattern for **timetable** (scoped to class for parent/student). **Student transcripts** require guardian/student/staff relationship; non-staff only see **published** transcript rows. **Fee status API** ignores soft-deleted fees.  
- **ID card view:** lookup is `school`-scoped first (no cross-tenant ID enumeration).  
- **`production_check` management command:** fails deploy if `DEBUG`, weak `SECRET_KEY`, open `ALLOWED_HOSTS`, in-memory Celery broker in prod, or missing `CSRF_TRUSTED_ORIGINS`.

---

## 4. Roles and permissions

### Current model

Roles appear in `accounts.models` (e.g. `school_admin`, `teacher`, `accountant`, `parent`, `student`, `super_admin`, plus HOD, deputy, etc.).

### Gaps

- **Per-school configurable permission matrix** (your spec): needs a `SchoolRolePermission` or policy table + UI; not fully verified in this pass.  
- Explicit matrix for **exam officer**, **receptionist**, **class teacher** vs **subject teacher** — confirm naming matches `User.role` and teaching assignments (`StaffTeachingAssignment`).

### Recommendation

- Add a single **permission service** that resolves `(user, school, capability)` and call it from decorators for both HTML and API views.

---

## 5. Speed improvements (implementation backlog)

| Item | Status |
|------|--------|
| Dashboard caching | Present |
| Query optimization (`select_related` / `prefetch_related`) | Partial — audit hot paths |
| Background jobs (Celery) | Present — extend for PDF/CSV bulk |
| Image compression | OMR pipeline; general uploads TBD |
| Lazy tables / server pagination | Partial |
| Memoized frontend | N/A for primary Django templates |
| Smaller API payloads | API-by-API review |
| Loading skeletons | Template-by-template |
| Queues for bulk SMS/email/OMR | Celery-ready; wire all producers |

---

## 6. Error handling

### Gaps

- **Global exception middleware** or structured logging to Sentry/OpenTelemetry (if desired).  
- **User-facing** copy for Paystack/webhook failures (some paths exist; unify).  
- **Retry** for idempotent webhooks and outbound SMS.

### This pass

- Clear **upload error messages** returned to the user from OMR flows.

---

## 7. Audit logs

### Current

- `audit.models.AuditLog` with `changes` JSON, IP, user agent, `request_id`, school indexes.  
- `AuditLog.log_action` helper.

### Gaps

- Not all **score/fee/payment** mutations may call `log_action` (verify signals or explicit calls).  
- **OMR manual corrections** should log old/new answers with user + IP.

### Recommendation

- Use **django-simple-history** or signals on `Fee`, `FeePayment`, `AssessmentScore`, `StudentReportCardScore`, `OmrResult` for consistency.

---

## 8. School setup improvements

### Current

- Schools, classes, subjects, terms, fee structures exist in models.  
- Feature flags gate modules.

### Gaps

- **Single guided setup wizard** (stepper: profile → branches → academic year → terms → grading → fees → comms) — confirm if a dedicated wizard app exists; if not, treat as build item.

---

## 9. Academic features

### Current

- Terms, subjects, timetable models, quizzes, online exams (`ExamAttempt`), OMR, manual scores, scheme-based report cards (`SchemeBasedGradingService`), PDF report generation (`academics/pdf_report.py`).

### Gaps

- **Class promotion** / bulk transfer UX and audit.  
- **Lesson notes / scheme of work** depth varies by deployment.  
- **Transcript across terms** — ensure read path aggregates `StudentReportCardScore` history.

---

## 10. Assessment / report cards

### Current

- `AssessmentScheme` + items; CA/Exam weights; multiple source types including OMR.  
- `StudentReportCardScore` stores contributions and `calculated_at`.

### Gaps

- **Regression tests** for every `source_type` branch in `_raw_score_for_item`.  
- **Lock published results** + correction workflow with mandatory audit.  
- **Preview before publish** flag on scheme or term batch.

---

## 11. Attendance

### Current

- `StudentAttendance`, `TeacherAttendance` referenced from dashboards.

### Gaps

- Subject-level attendance, termly roll-up on PDF report card, parent push for absence — verify coverage in `operations` and templates.

---

## 12. Finance

### Current

- Fees, partial payments, Paystack, discounts/workflow models (ERP migrations present).  
- Debtor-style views depend on school configuration.

### This pass

- Dashboard and parent detail **fee totals** ignore archived (soft-deleted) fee rows.  
- **Indexes** on `FeePayment` for school + status/time reporting.

### Gaps

- Payment delete policy: enforce **permission + audit** only (no silent hard delete in UI).

---

## 13. Communication

### Current

- Messaging / outbound comm logs (RLS migration references).

### Gaps

- **Delivery status** for bulk SMS, template library, fee reminder scheduler — confirm against `operations` / `core/tasks.py`.

---

## 14. Parent / student portal

### Gaps

- Ensure every portal query includes **`school` + relationship** guards (parent ↔ student).  
- Surface timetable, behavior, teacher messages consistently.

---

## 15. Staff management

### Current

- HR utilities, contracts, payroll Paystack hooks, teaching assignments in `accounts`.

### Gaps

- Leave workflow approvals tied to audit log.

---

## 16. Student management

### Current

- Rich student profile, guardians, medical fields, exit workflow, soft delete.

### Gaps

- Admission form PDF/export and document vault retention policy.

---

## 17. Optional modules

Inventory/library/transport/hostel: verify `INSTALLED_APPS` and migrations for your SKU; enable via feature flags.

---

## 18. Notifications and reminders

Celery beat schedules exist; map each business reminder to a task and template.

---

## 19. Data import/export

### Gaps

- Central **import validation report** (row-level errors) before commit; sample CSV templates in `static/` or admin docs.

---

## 20. Backups and reliability

### This pass

- **Management command:** `python manage.py backup_database`  
  - SQLite: file copy to `BACKUPS_DIR` or `schoolms/backups/`.  
  - PostgreSQL: `pg_dump` when client tools are installed.  
- **Restore:** document in runbook (not automated here).

### Existing

- Health/ready endpoints.  
- Celery task time limits in settings.

---

## 21. UI/UX

### Gaps

- Breadcrumbs, global search (partial search API exists in `accounts/views.py` around fee/staff results), mobile nav audit.  
- Destructive action modals — template-by-template.

---

## 22. Reports

Many reports can be built as filtered list views + CSV export; ensure accountant-only routes.

---

## 23. OMR

### Current

- Pipeline: quality gate, perspective, blank subtraction, CC scoring, calibration with geometry JSON, debug artifacts, tests (`omr/tests/test_pipeline.py`).

### Gaps

- Batch queue for hundreds of sheets; storage lifecycle for debug PNGs; AI assist for low confidence (optional).

---

## 24. Developer / code quality

### Gaps

- API documentation (OpenAPI) if exposing large DRF surface.  
- `ENVIRONMENT.md` listing: `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `OMR_MAX_UPLOAD_BYTES`, Paystack keys, `NUM_PROXIES` for IP.

---

## 25. Testing

### Recommended critical tests (build out)

| Area | Suggested test module |
|------|------------------------|
| Login + roles | `accounts/tests` |
| Tenant isolation | `core/tests` or per-app |
| Fee payment + webhooks | `finance/tests` |
| Report card math | `academics/tests` for `SchemeBasedGradingService` |
| OMR scoring | `omr/tests` |
| CSV import | `students/tests` or `operations/tests` |
| Audit log | `audit/tests` |

### This pass

- `core/tests/test_upload_validation.py` — extension, size, and skip-verify paths.

---

## Bugs fixed (this pass)

1. **Dashboard fee metrics** could include **soft-deleted (archived) fee** rows in sums and “unpaid” counts — fixed by filtering `deleted_at__isnull=True` in dashboard and related aggregates (super-admin dashboard, school dashboard, parent child fee summary, global search fees).  
2. **API `/api/v1/results/`** allowed any authenticated user with a school to list **all students’** published results (privacy / compliance gap).  
3. **`/api/v1/timetable/`** used non-existent fields `day` / `period` on `Timetable` (would error at runtime) and exposed the full school timetable to any school user.  
4. **`/api/v1/students/<id>/transcripts/`** did not verify parent/guardian or student identity; **unpublished** transcripts could be read by anyone with the student ID.  
5. **`StudentTranscript` API ordering** referenced non-existent `term__order` (replaced with `term__id`).  
6. **`student_payment_history`** allowed any same-school user (e.g. parents browsing other children) when only a loose school match was applied; superusers without `school` could bypass checks.  
7. **Assignment grading/download** fetched submissions by primary key only, then redirected — weaker than a single scoped `get_object_or_404`.

## Performance improvements (this pass)

1. Exclude archived fees from key aggregates (cleaner, faster intent-aligned queries).  
2. Database indexes for **student class rosters** and **fee payment reporting**.  
3. OMR: reject invalid uploads before disk write and CV work.

## Database indexes added (this pass)

| Table / model | Index | Migration |
|---------------|-------|-----------|
| `students_student` | `(school_id, school_class_id, status)` | `students/migrations/0021_student_school_class_status_idx.py` |
| `finance_feepayment` | `(school_id, status, paid_at)` | `finance/migrations/0035_feepayment_school_status_created_indexes.py` |
| `finance_feepayment` | `(school_id, created_at)` | same |

*Run:* `python manage.py migrate` from `schoolms/` when Python is available.

## Security improvements (this pass)

1. **OMR image uploads:** type/size validation + integrity check (Pillow when installed).
2. **Calibration blank sheet:** invalid image no longer overwrites stored blank silently; user gets a warning.
3. **API scoping** for results, timetable, transcripts (see §3).
4. **`can_api_list_schoolwide_published_results`** in `accounts/permissions.py` — explicit rule for who may see school-wide published academics via API.  
5. **Student payment history** (`operations/payment_views.py`): strict rules — finance/leadership/staff scoped by school; **parent** only with `parent_is_guardian_of`; **student** only self; **superuser** cross-tenant; fee rows exclude soft-deleted.  
6. **Assignment submission** grade/download: `get_object_or_404` filtered by `homework__subject__school` (no cross-tenant fetch + redirect).  
7. **`exam_officer` role** added to `User` choices and `STAFF_ROLES`; included in school dashboard routing, HR staff lists, API published-results access, and exam-hall permission.  
8. **JWT obtain** (`/api/token/`) rate-limited (`token_obtain`: 30/min per IP) via `ThrottledTokenObtainPairView`.  
9. **`ExceptionLoggingMiddleware`** — logs unhandled exceptions to `mastex.unhandled` (console/file + admin email when configured).  
10. **`audit_security_gaps`** management command — runs `production_check` via subprocess and prints a release checklist.

## New or improved features (this pass)

1. **`core/upload_validation.py`** — reusable validation for image uploads.
2. **`backup_database` management command** — SQLite copy / Postgres `pg_dump`.
3. **`production_check` management command** — production settings gate.
4. **Composite DB indexes** for students and fee payments.
5. **`integrations/tests/test_api_privacy.py`** — regression tests for API privacy rules.
6. **`operations/tests.py`** — `StudentPaymentHistoryAccessTests` for guardian enforcement.

## Environment variables (quick reference)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Production DB (dj-database-url) |
| `REDIS_URL` | Cache + Celery broker default |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Task queue |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | Django upload cap |
| `OMR_MAX_UPLOAD_BYTES` | Optional stricter cap for OMR images |
| `KEEP_RAW_SCANS_DAYS` / `KEEP_DEBUG_OVERLAYS_DAYS` | OMR temp/debug retention (see `OMR_*_RETENTION_HOURS`) |
| `ENABLE_DEBUG_OVERLAYS` | When false, OMR writes no debug PNGs (production default off) |
| `ENABLE_RAW_SCAN_STORAGE` | When false, temp scan retention capped aggressively |
| `AUTO_CLEANUP_ENABLED` | When false, scheduled OMR media cleanup no-ops |
| `MEDIA_IMAGE_MAX_DIMENSION` / `MEDIA_JPEG_QUALITY` | Optional upload compression (`core.media_utils`) |
| `NUM_PROXIES` | Trusted proxy depth for IP (login rate limit, audit) |
| `BACKUP_DIR` | Optional override for backup output directory |
| `DJANGO_DEBUG` | Must be false in production |

---

## Enterprise hardening pass (2026-05-06)

1. **Result workflow** — `Result.workflow_status` (draft → reviewed → approved → published → locked), index `(school, workflow_status)`. Locked rows reject score edits via `full_clean()` unless workflow is moved out of locked.  
2. **Score audit** — append-only `ScoreChangeLog` + automatic logs on `Result.save()` when `score` / `total_score` / `remarks` change.  
3. **Publish gate** — bulk publish/unpublish in `result_list` requires `can_publish_academic_results` (head / deputy / exam officer).  
4. **Report card snapshots** — `ReportCard.calculation_snapshot` populated when a PDF is generated with `publish=1` (`freeze_report_card_calculation`).  
5. **Finance void** — `FeePayment.voided_at` / `voided_by` / `void_reason`; first void subtracts from `Fee.amount_paid` and writes `audit.write_audit`.  
6. **Async job registry** — `core.AsyncJob` + admin for operational visibility (pair with Celery).  
7. **Health** — `/health/` includes cache ping + `debug` flag.  
8. **Tasks** — `recompute_assessment_scheme_task` (Celery) for heavy scheme recomputation.  
9. **Media** — `core/media_utils.compress_image_bytes` for optional JPEG optimisation.

**Remaining debt:** full approval UI (reviewed/approved transitions), django-celery-results or Flower for queue graphs, finance void admin workflow + Paystack reversal integration, parent portal perf pass.

## Next recommended sprints (short)

1. **Mechanical URL audit** — extend tooling beyond template `{% url %}` checks to flag views missing auth or school filters (heuristic).  
2. **Wire Celery** for bulk report card ZIP and large CSV exports (stubs added).  
3. **Expand void workflow** — UI, dual-control approval, Paystack refund linkage.  
4. **Setup wizard** — one URL, persisted `SetupStep` state per school.

---

## Production readiness (how to interpret “100%”)

No large web application is “mathematically complete” without **your** environment, data, and UAT. This codebase now includes **layered controls**: tenant-scoped APIs, guardian checks on sensitive finance views, upload validation, deploy gates (`production_check`, `audit_security_gaps`), structured error logging, backups, DB indexes, and automated tests for the highest-risk regressions found during audit.

**Before calling a release “production-ready”, run:**

1. `python manage.py migrate`  
2. `python manage.py production_check` (with production-like env)  
3. `python manage.py test` (full suite)  
4. `python manage.py audit_security_gaps`  
5. Smoke tests on staging: parent portal, staff dashboard, Paystack callbacks, OMR upload.

---

*End of SYSTEM_AUDIT.md — update as features land.*
