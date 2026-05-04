"""
OMR Analysis Service
====================
Generates class-level statistics from OmrResult queryset.
"""

from __future__ import annotations

from django.db.models import QuerySet


def get_exam_analysis(results_qs: QuerySet) -> dict:
    """
    Build analysis data from a queryset of OmrResult objects.

    Returns a dict with:
        total_students, average_score, average_percentage,
        highest_percentage, lowest_percentage, pass_count, fail_count,
        score_distribution, question_performance (per-question stats),
        top_missed_questions
    """
    results = list(results_qs.values(
        "student_name",
        "score",
        "total_questions",
        "percentage",
        "correct_count",
        "wrong_count",
        "blank_count",
        "multiple_answer_count",
        "per_question_result",
    ))

    if not results:
        return _empty_analysis()

    total_students = len(results)
    percentages = [r["percentage"] for r in results]
    scores = [r["score"] for r in results]

    average_percentage = round(sum(percentages) / total_students, 2)
    highest_percentage = round(max(percentages), 2)
    lowest_percentage = round(min(percentages), 2)
    average_score = round(sum(scores) / total_students, 2)

    pass_count = sum(1 for p in percentages if p >= 50)
    fail_count = total_students - pass_count

    # Score distribution buckets (0-9, 10-19, ..., 90-100)
    buckets = {f"{i*10}-{i*10+9}%": 0 for i in range(10)}
    buckets["100%"] = 0
    for p in percentages:
        if p == 100:
            buckets["100%"] += 1
        else:
            bucket = f"{int(p // 10) * 10}-{int(p // 10) * 10 + 9}%"
            if bucket in buckets:
                buckets[bucket] += 1

    # Per-question performance
    q_stats: dict[str, dict] = {}
    for r in results:
        pqr = r.get("per_question_result") or {}
        for q_str, q_data in pqr.items():
            if q_str not in q_stats:
                q_stats[q_str] = {"correct": 0, "wrong": 0, "blank": 0, "multiple": 0, "total": 0}
            q_stats[q_str]["total"] += 1
            status = q_data.get("status", "wrong")
            if status in q_stats[q_str]:
                q_stats[q_str][status] += 1

    question_performance = []
    for q_str in sorted(q_stats.keys(), key=lambda x: int(x)):
        s = q_stats[q_str]
        total_q = s["total"] or 1
        question_performance.append({
            "question": int(q_str),
            "correct": s["correct"],
            "wrong": s["wrong"],
            "blank": s["blank"],
            "multiple": s["multiple"],
            "correct_pct": round(s["correct"] / total_q * 100, 1),
        })

    top_missed = sorted(
        question_performance,
        key=lambda q: q["correct_pct"]
    )[:10]

    ranking = sorted(
        [
            {
                "student_name": r["student_name"],
                "score": r["score"],
                "total_questions": r["total_questions"],
                "percentage": r["percentage"],
                "correct_count": r["correct_count"],
                "wrong_count": r["wrong_count"],
                "blank_count": r["blank_count"],
            }
            for r in results
        ],
        key=lambda x: (-x["percentage"], x["student_name"]),
    )

    return {
        "total_students": total_students,
        "average_score": average_score,
        "average_percentage": average_percentage,
        "highest_percentage": highest_percentage,
        "lowest_percentage": lowest_percentage,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate": round(pass_count / total_students * 100, 1) if total_students else 0,
        "score_distribution": buckets,
        "question_performance": question_performance,
        "top_missed_questions": top_missed,
        "ranking": ranking[:50],
    }


def _empty_analysis() -> dict:
    return {
        "total_students": 0,
        "average_score": 0,
        "average_percentage": 0,
        "highest_percentage": 0,
        "lowest_percentage": 0,
        "pass_count": 0,
        "fail_count": 0,
        "pass_rate": 0,
        "score_distribution": {},
        "question_performance": [],
        "top_missed_questions": [],
        "ranking": [],
    }
