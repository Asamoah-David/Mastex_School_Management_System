import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("schools", "0019_alter_schoolfeature_key"),
        ("students", "0020_erp_new_models_batch"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OmrExam",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("subject", models.CharField(max_length=100)),
                ("class_name", models.CharField(max_length=100)),
                ("date", models.DateField()),
                (
                    "template_type",
                    models.CharField(
                        choices=[("basic_30_ad", "30 Questions (A–D)"), ("bece_60_ae", "60 Questions (A–E)")],
                        max_length=50,
                    ),
                ),
                ("total_questions", models.PositiveIntegerField()),
                ("answer_key", models.JSONField(blank=True, null=True)),
                ("answer_key_confirmed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="omr_exams_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="omr_exams",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "OMR Exam",
                "verbose_name_plural": "OMR Exams",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="OmrResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("student_name", models.CharField(blank=True, max_length=200)),
                ("class_name", models.CharField(blank=True, max_length=100)),
                ("subject", models.CharField(blank=True, max_length=100)),
                ("template_type", models.CharField(blank=True, max_length=50)),
                ("detected_answers", models.JSONField(default=dict)),
                ("answer_key", models.JSONField(default=dict)),
                ("per_question_result", models.JSONField(default=dict)),
                ("score", models.FloatField(default=0)),
                ("total_questions", models.PositiveIntegerField(default=0)),
                ("percentage", models.FloatField(default=0)),
                ("correct_count", models.IntegerField(default=0)),
                ("wrong_count", models.IntegerField(default=0)),
                ("blank_count", models.IntegerField(default=0)),
                ("multiple_answer_count", models.IntegerField(default=0)),
                ("flagged_questions", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="omr_results_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "exam",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="omr.omrexam",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="omr_results",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="omr_results",
                        to="students.student",
                    ),
                ),
            ],
            options={
                "verbose_name": "OMR Result",
                "verbose_name_plural": "OMR Results",
                "ordering": ["-percentage", "student_name"],
            },
        ),
    ]
