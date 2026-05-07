import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("omr", "0004_omrexam_deleted_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="OmrTemplateCalibration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("template_id", models.CharField(db_index=True, max_length=64)),
                ("template_name", models.CharField(blank=True, max_length=200)),
                ("calibrated_config", models.JSONField(blank=True, default=dict)),
                ("blank_sheet", models.ImageField(blank=True, null=True, upload_to="omr/blanks/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="omr_template_calibrations",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "OMR template calibration",
                "verbose_name_plural": "OMR template calibrations",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="omrtemplatecalibration",
            constraint=models.UniqueConstraint(
                fields=("school", "template_id"),
                name="uniq_omr_calibration_school_template",
            ),
        ),
        migrations.AddField(
            model_name="omrresult",
            name="raw_cv_answers",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="omrresult",
            name="cv_per_question",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="omrresult",
            name="uncertain_count",
            field=models.IntegerField(default=0),
        ),
    ]
