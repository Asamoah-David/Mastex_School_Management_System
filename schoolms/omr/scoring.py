"""
OMR Scoring Service
===================
Pure functions — no DB access, no side effects.
"""

from __future__ import annotations


def calculate_score(
    detected_answers: dict[str, str],
    answer_key: dict[str, str],
    total_questions: int,
) -> dict:
    """
    Compare detected answers against the answer key and return score data.

    Parameters
    ----------
    detected_answers : {"1": "A", "2": "blank", "3": "multiple", ...}
    answer_key       : {"1": "A", "2": "C", ...}
    total_questions  : int

    Returns
    -------
    {
        "score": float,
        "total_questions": int,
        "percentage": float,
        "correct_count": int,
        "wrong_count": int,
        "blank_count": int,
        "multiple_answer_count": int,
        "per_question_result": {...},
    }
    """
    per_q: dict[str, dict] = {}
    correct = wrong = blank = multiple = 0

    for q in range(1, total_questions + 1):
        q_str = str(q)
        student_ans = detected_answers.get(q_str, "blank")
        correct_ans = answer_key.get(q_str, "")

        if student_ans == "blank":
            status = "blank"
            blank += 1
        elif student_ans == "multiple":
            status = "multiple"
            multiple += 1
        elif student_ans.upper() == correct_ans.upper():
            status = "correct"
            correct += 1
        else:
            status = "wrong"
            wrong += 1

        per_q[q_str] = {
            "student_answer": student_ans,
            "correct_answer": correct_ans,
            "status": status,
        }

    score = float(correct)
    percentage = round(score / total_questions * 100, 2) if total_questions > 0 else 0.0

    return {
        "score": score,
        "total_questions": total_questions,
        "percentage": percentage,
        "correct_count": correct,
        "wrong_count": wrong,
        "blank_count": blank,
        "multiple_answer_count": multiple,
        "per_question_result": per_q,
    }


def apply_manual_corrections(
    original_answers: dict[str, str],
    corrections: dict[str, str],
) -> dict[str, str]:
    """
    Merge teacher corrections into detected answers.
    corrections keys are question numbers as strings.
    """
    merged = dict(original_answers)
    for q_str, new_ans in corrections.items():
        if new_ans:
            merged[q_str] = new_ans.upper() if new_ans not in ("blank", "multiple") else new_ans
    return merged


def grade_label(percentage: float, boundaries: list[tuple] | None = None) -> str:
    """Return a letter grade for a percentage. Uses simple defaults."""
    boundaries = boundaries or [
        (80, "A"), (70, "B"), (60, "C"), (50, "D"), (0, "F")
    ]
    for threshold, label in boundaries:
        if percentage >= threshold:
            return label
    return "F"
