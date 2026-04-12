"""Single place for default academic year / current term labels."""
from __future__ import annotations


def get_current_term_for_school(school):
    """Return the Term marked current for this school, or None."""
    if not school:
        return None
    from academics.models import Term

    return Term.objects.filter(school=school, is_current=True).order_by("-id").first()


def default_academic_year_label(school) -> str:
    """Prefer School.academic_year; else derive from current term name or calendar year."""
    if school and getattr(school, "academic_year", None):
        return (school.academic_year or "").strip()
    term = get_current_term_for_school(school)
    if term and term.name:
        return term.name.strip()
    from django.utils import timezone

    y = timezone.now().year
    return f"{y}/{y + 1}"
