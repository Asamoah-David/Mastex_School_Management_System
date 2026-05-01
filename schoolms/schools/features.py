from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect

from core.utils import get_effective_school
from .models import SchoolFeature


# ---------------------------------------------------------------------------
# Feature Registry — metadata for every feature flag
# ---------------------------------------------------------------------------
# Structure: key → {label, description, category, min_plan, icon (Bootstrap/FA class)}
# min_plan: "basic" | "standard" | "premium"
FEATURE_REGISTRY: dict[str, dict] = {
    # ── Academics ───────────────────────────────────────────────────────────
    "results": {
        "label": "Results & Report Cards",
        "description": "Capture exam results and generate academic report cards per term.",
        "category": "Academics",
        "min_plan": "basic",
        "icon": "bi-award",
    },
    "exams": {
        "label": "Exam Scheduling",
        "description": "Schedule examinations, assign halls, and manage seating plans.",
        "category": "Academics",
        "min_plan": "basic",
        "icon": "bi-journal-check",
    },
    "online_exams": {
        "label": "Online Exams",
        "description": "Create and run auto-graded online assessments with anti-cheat controls.",
        "category": "Academics",
        "min_plan": "standard",
        "icon": "bi-laptop",
    },
    "homework": {
        "label": "Homework / Assignments",
        "description": "Set, collect, and grade student homework online.",
        "category": "Academics",
        "min_plan": "basic",
        "icon": "bi-pencil-square",
    },
    "quiz": {
        "label": "Quizzes",
        "description": "Quick in-class quizzes with instant scoring.",
        "category": "Academics",
        "min_plan": "basic",
        "icon": "bi-question-circle",
    },
    "timetable": {
        "label": "Timetable",
        "description": "Build and publish weekly class timetables with conflict detection.",
        "category": "Academics",
        "min_plan": "basic",
        "icon": "bi-calendar3",
    },
    "performance_analytics": {
        "label": "Performance Analytics",
        "description": "Visual dashboards and trend analysis for student academic performance.",
        "category": "Academics",
        "min_plan": "standard",
        "icon": "bi-graph-up",
    },
    # ── Admissions & Students ────────────────────────────────────────────────
    "admission": {
        "label": "Admissions",
        "description": "Online admission application portal with public referral links.",
        "category": "Admissions & Students",
        "min_plan": "basic",
        "icon": "bi-person-plus",
    },
    "student_enrollment": {
        "label": "Student Enrollment",
        "description": "Enrol students into classes and manage their academic records.",
        "category": "Admissions & Students",
        "min_plan": "basic",
        "icon": "bi-person-badge",
    },
    "documents": {
        "label": "Student Documents",
        "description": "Upload and manage student-level documents (birth certificates, etc.).",
        "category": "Admissions & Students",
        "min_plan": "basic",
        "icon": "bi-file-earmark-text",
    },
    "certificates": {
        "label": "Certificates",
        "description": "Generate and print completion and achievement certificates.",
        "category": "Admissions & Students",
        "min_plan": "standard",
        "icon": "bi-patch-check",
    },
    "id_cards": {
        "label": "ID Cards",
        "description": "Auto-generate student and staff ID cards.",
        "category": "Admissions & Students",
        "min_plan": "standard",
        "icon": "bi-credit-card",
    },
    "discipline": {
        "label": "Discipline Records",
        "description": "Log incidents, track behavior points, and maintain discipline history.",
        "category": "Admissions & Students",
        "min_plan": "basic",
        "icon": "bi-shield-exclamation",
    },
    "health_records": {
        "label": "Health Records",
        "description": "Store student health info, allergies, and clinic visit records.",
        "category": "Admissions & Students",
        "min_plan": "standard",
        "icon": "bi-heart-pulse",
    },
    "alumni": {
        "label": "Alumni Tracking",
        "description": "Track graduates, their careers, university placements, and donations.",
        "category": "Admissions & Students",
        "min_plan": "standard",
        "icon": "bi-mortarboard",
    },
    # ── Operations ───────────────────────────────────────────────────────────
    "attendance": {
        "label": "Student Attendance",
        "description": "Daily student attendance marking and absence notifications.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-check2-all",
    },
    "teacher_attendance": {
        "label": "Staff Attendance",
        "description": "Track teacher/staff daily attendance and punctuality.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-person-check",
    },
    "bus_transport": {
        "label": "Bus Transport",
        "description": "Bus routes, student allocations, and transport fee collection.",
        "category": "Operations",
        "min_plan": "standard",
        "icon": "bi-bus-front",
    },
    "canteen": {
        "label": "Canteen / POS",
        "description": "Canteen menu, pre-order system, and payment tracking.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-shop",
    },
    "textbooks": {
        "label": "Textbooks",
        "description": "Textbook catalogue, issue tracking, and sale collection.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-book",
    },
    "hostel": {
        "label": "Hostel / Dormitory",
        "description": "Manage hostel rooms, assignments, and boarding fees.",
        "category": "Operations",
        "min_plan": "standard",
        "icon": "bi-building",
    },
    "library": {
        "label": "Library",
        "description": "Book catalogue, issue/return tracking, and overdue fines.",
        "category": "Operations",
        "min_plan": "standard",
        "icon": "bi-journal-bookmark",
    },
    "inventory": {
        "label": "Inventory",
        "description": "Track school supplies and equipment with low-stock alerts.",
        "category": "Operations",
        "min_plan": "standard",
        "icon": "bi-box-seam",
    },
    "academic_calendar": {
        "label": "Academic Calendar",
        "description": "Plan and publish term dates, holidays, and exam windows.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-calendar-event",
    },
    "school_events": {
        "label": "School Events",
        "description": "Create and manage school events with RSVP tracking.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-flag",
    },
    "sports": {
        "label": "Sports",
        "description": "Manage sports teams, tournaments, and student participation.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-trophy",
    },
    "clubs": {
        "label": "Clubs & Activities",
        "description": "Manage extracurricular clubs with enrolment controls.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-people",
    },
    "pt_meetings": {
        "label": "Parent-Teacher Meetings",
        "description": "Schedule PT meetings with slot booking and optional video call links.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-camera-video",
    },
    "announcements": {
        "label": "Announcements",
        "description": "Broadcast school-wide or targeted announcements.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-megaphone",
    },
    # ── Finance ──────────────────────────────────────────────────────────────
    "fee_management": {
        "label": "Fee Management",
        "description": "Configure fee structures, assign fees to students, and track payment.",
        "category": "Finance",
        "min_plan": "basic",
        "icon": "bi-currency-dollar",
    },
    "online_payments": {
        "label": "Online Payments (Paystack)",
        "description": "Accept fee payments online via Paystack (card, mobile money).",
        "category": "Finance",
        "min_plan": "standard",
        "icon": "bi-credit-card-2-front",
    },
    "expenses": {
        "label": "Expense Tracking",
        "description": "Record, approve, and report on school operational expenses.",
        "category": "Finance",
        "min_plan": "standard",
        "icon": "bi-receipt",
    },
    "budgets": {
        "label": "Budget Management",
        "description": "Set budgets per category and track actual vs. planned spending.",
        "category": "Finance",
        "min_plan": "standard",
        "icon": "bi-pie-chart",
    },
    "finance_admin": {
        "label": "Finance Administration",
        "description": "Full finance admin: ledger, settlements, purchase orders, asset register.",
        "category": "Finance",
        "min_plan": "premium",
        "icon": "bi-bank",
    },
    # ── HR ───────────────────────────────────────────────────────────────────
    "staff_management": {
        "label": "Staff Management",
        "description": "Staff profiles, contracts, teaching assignments, and performance reviews.",
        "category": "HR",
        "min_plan": "basic",
        "icon": "bi-person-lines-fill",
    },
    "leave_management": {
        "label": "Leave Management",
        "description": "Staff leave requests, approvals, balance tracking, and accrual.",
        "category": "HR",
        "min_plan": "standard",
        "icon": "bi-calendar-x",
    },
    "staff_paystack_transfers": {
        "label": "Staff Payroll Transfers",
        "description": "Disburse salary payments directly to staff via Paystack transfers.",
        "category": "HR",
        "min_plan": "premium",
        "icon": "bi-send",
    },
    # ── Communication & AI ───────────────────────────────────────────────────
    "messaging": {
        "label": "SMS Messaging",
        "description": "Send bulk SMS to parents, staff, or custom groups.",
        "category": "Communication",
        "min_plan": "standard",
        "icon": "bi-chat-dots",
    },
    "ai_assistant": {
        "label": "AI Assistant",
        "description": "AI-powered teacher assistant for lesson plans, comments, and Q&A.",
        "category": "Communication",
        "min_plan": "premium",
        "icon": "bi-robot",
    },
    # ── New Feature Models (Session 8) ──────────────────────────────────────
    "question_bank": {
        "label": "Question Bank",
        "description": "Reusable question repository per subject; pull questions into exams automatically.",
        "category": "Academics",
        "min_plan": "standard",
        "icon": "bi-collection",
    },
    "learning_plans": {
        "label": "Individual Learning Plans (IEP/SEN)",
        "description": "Document and track personalised learning plans for SEN, gifted, or remedial students.",
        "category": "Student Services",
        "min_plan": "standard",
        "icon": "bi-journal-medical",
    },
    "early_warning": {
        "label": "Early Warning System",
        "description": "Automated at-risk detection based on attendance, grades, and discipline signals.",
        "category": "Student Services",
        "min_plan": "premium",
        "icon": "bi-exclamation-triangle",
    },
    "report_cards": {
        "label": "Digital Report Cards",
        "description": "Generate, publish, and securely share PDF report cards per term.",
        "category": "Academics",
        "min_plan": "basic",
        "icon": "bi-file-earmark-text",
    },
    "scholarships": {
        "label": "Scholarships & Bursaries",
        "description": "Manage scholarship programmes, track awards, and link to fee discounts.",
        "category": "Finance",
        "min_plan": "standard",
        "icon": "bi-mortarboard",
    },
    "class_supplies": {
        "label": "Class Supply Tracker",
        "description": "Request and track school supplies from students per class; parents see pending items.",
        "category": "Operations",
        "min_plan": "basic",
        "icon": "bi-bag-check",
    },
    "job_portal": {
        "label": "Job Portal (Recruitment)",
        "description": "Post open positions for teachers and staff; accept applications with Paystack payment.",
        "category": "HR",
        "min_plan": "standard",
        "icon": "bi-briefcase",
    },
}

# Convenience set of all keys (used by ensure_features_exist)
DEFAULT_FEATURE_KEYS: tuple[str, ...] = tuple(FEATURE_REGISTRY.keys())


# Convenience: group by category for admin/setup UI rendering
def get_features_by_category() -> dict[str, list[dict]]:
    """Return features grouped by category, each item enriched with its key."""
    grouped: dict[str, list] = {}
    for key, meta in FEATURE_REGISTRY.items():
        cat = meta["category"]
        grouped.setdefault(cat, []).append({"key": key, **meta})
    return grouped



def is_feature_enabled(request, key: str) -> bool:
    school = get_effective_school(request)
    if not school:
        return True

    flags = getattr(request, "_feature_flags_cache", None)
    if flags is None:
        from django.core.cache import cache as _cache
        cache_key = f"school_features:{school.pk}"
        flags = _cache.get(cache_key)
        if flags is None:
            flags = dict(
                SchoolFeature.objects.filter(school=school).values_list("key", "enabled")
            )
            _cache.set(cache_key, flags, 300)
        request._feature_flags_cache = flags

    enabled = flags.get(key)
    return True if enabled is None else bool(enabled)


def require_feature(request, key: str, fallback_url_name: str = "home"):
    if is_feature_enabled(request, key):
        return None
    try:
        messages.error(request, "This feature is disabled for your school. Please contact the platform administrator.")
    except Exception:
        pass
    return redirect(fallback_url_name)


def ensure_features_exist(school) -> None:
    existing = set(SchoolFeature.objects.filter(school=school).values_list("key", flat=True))
    missing = [k for k in DEFAULT_FEATURE_KEYS if k not in existing]
    if not missing:
        return
    SchoolFeature.objects.bulk_create([SchoolFeature(school=school, key=k, enabled=True) for k in missing])

