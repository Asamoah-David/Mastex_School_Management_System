"""Freeze scheme-based calculations onto a ReportCard for historical integrity."""

from __future__ import annotations

from typing import Any


def build_calculation_snapshot(*, student, term) -> dict[str, Any]:
    """Return serialisable breakdown from current StudentReportCardScore rows."""
    from .models import StudentReportCardScore

    rows = (
        StudentReportCardScore.objects.filter(student=student, term=term)
        .select_related("subject", "scheme")
        .order_by("subject__name")
    )
    return {
        "student_id": student.pk,
        "term_id": term.pk if term else None,
        "generated_from": "StudentReportCardScore",
        "subjects": [
            {
                "subject": r.subject.name if r.subject_id else "",
                "subject_id": r.subject_id,
                "scheme_id": r.scheme_id,
                "ca_raw_score": r.ca_raw_score,
                "ca_total_possible": r.ca_total_possible,
                "ca_contribution": r.ca_contribution,
                "exam_raw_score": r.exam_raw_score,
                "exam_total_possible": r.exam_total_possible,
                "exam_contribution": r.exam_contribution,
                "final_score": r.final_score,
                "status": r.status,
            }
            for r in rows
        ],
    }


def freeze_report_card_calculation(report_card) -> None:
    """Populate ``calculation_snapshot`` from live report-card scores (call when publishing)."""
    if not report_card.student_id or not report_card.term_id:
        return
    from .models import ReportCard

    snap = build_calculation_snapshot(
        student=report_card.student,
        term=report_card.term,
    )
    ReportCard.objects.filter(pk=report_card.pk).update(calculation_snapshot=snap)
