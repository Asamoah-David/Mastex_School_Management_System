from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_alter_user_role"),
        ("schools", "0003_school_logo_url_academic_year"),
        ("students", "0004_schoolclass"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("graduated", "Graduated / Alumni"),
                    ("withdrawn", "Withdrawn / Transferred"),
                    ("dismissed", "Dismissed / Expelled"),
                ],
                default="active",
                help_text="Use this instead of deleting students so history is preserved.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="student",
            name="exit_date",
            field=models.DateField(
                blank=True,
                help_text="Date the student left, graduated, or was dismissed.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="student",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"role": "parent"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="children",
                to="accounts.user",
            ),
        ),
        migrations.CreateModel(
            name="AbsenceRequest",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(help_text="Date the student will be absent.")),
                ("reason", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="absence_requests_reviewed",
                        to="accounts.user",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="schools.school"),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="absence_requests",
                        to="students.student",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
