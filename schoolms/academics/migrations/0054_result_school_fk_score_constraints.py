"""
Fix 7: Add Result.school FK (backfilled from student.school).
Fix 28: Add DB-level CheckConstraints to Result, AssessmentScore, ExamScore.
"""
from django.db import migrations, models
import django.db.models.deletion


def backfill_result_school(apps, schema_editor):
    Result = apps.get_model("academics", "Result")
    to_update = []
    for r in Result.objects.select_related("student").filter(school__isnull=True):
        if r.student_id and r.student.school_id:
            r.school_id = r.student.school_id
            to_update.append(r)
        if len(to_update) >= 500:
            Result.objects.bulk_update(to_update, ["school"])
            to_update = []
    if to_update:
        Result.objects.bulk_update(to_update, ["school"])


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0053_gradeboundary_term_fk"),
        ("schools", "0014_school_subscription_plan_logo"),
    ]

    operations = [
        # Fix 7: school FK on Result
        migrations.AddField(
            model_name="result",
            name="school",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="schools.school",
                help_text="Denormalised from student.school for efficient school-scoped queries.",
            ),
        ),
        migrations.RunPython(backfill_result_school, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="result",
            index=models.Index(fields=["school", "term"], name="idx_result_school_term"),
        ),
        # Fix 28: CheckConstraints — Result
        migrations.AddConstraint(
            model_name="result",
            constraint=models.CheckConstraint(
                check=models.Q(score__gte=0), name="chk_result_score_nonneg"
            ),
        ),
        migrations.AddConstraint(
            model_name="result",
            constraint=models.CheckConstraint(
                check=models.Q(total_score__gt=0), name="chk_result_total_score_pos"
            ),
        ),
        # Fix 28: CheckConstraints — AssessmentScore
        migrations.AddConstraint(
            model_name="assessmentscore",
            constraint=models.CheckConstraint(
                check=models.Q(score__gte=0), name="chk_ascore_score_nonneg"
            ),
        ),
        migrations.AddConstraint(
            model_name="assessmentscore",
            constraint=models.CheckConstraint(
                check=models.Q(max_score__gt=0), name="chk_ascore_max_pos"
            ),
        ),
        # Fix 28: CheckConstraints — ExamScore
        migrations.AddConstraint(
            model_name="examscore",
            constraint=models.CheckConstraint(
                check=models.Q(score__gte=0), name="chk_exscore_score_nonneg"
            ),
        ),
        migrations.AddConstraint(
            model_name="examscore",
            constraint=models.CheckConstraint(
                check=models.Q(max_score__gt=0), name="chk_exscore_max_pos"
            ),
        ),
    ]
