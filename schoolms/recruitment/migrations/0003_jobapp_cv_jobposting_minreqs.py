from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0002_jobapp_unique_interview_blank"),
    ]

    operations = [
        # JobPosting — minimum requirements fields
        migrations.AddField(
            model_name="jobposting",
            name="min_qualification",
            field=models.CharField(
                blank=True,
                choices=[
                    ("wassce", "WASSCE"),
                    ("ssce", "SSCE"),
                    ("diploma", "Diploma / HND"),
                    ("degree", "Bachelor's Degree"),
                    ("masters", "Master's Degree"),
                    ("phd", "PhD / Doctorate"),
                    ("professional", "Professional Certificate"),
                    ("other", "Other"),
                ],
                help_text="Minimum qualification required (leave blank for any)",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="jobposting",
            name="min_years_experience",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Minimum years of experience required (0 = any)",
            ),
        ),
        # JobApplication — CV upload + referees
        migrations.AddField(
            model_name="jobapplication",
            name="cv_upload",
            field=models.FileField(
                blank=True,
                null=True,
                help_text="CV/Resume (PDF, DOC, DOCX — max 5 MB)",
                upload_to="job_applications/cvs/",
            ),
        ),
        migrations.AddField(
            model_name="jobapplication",
            name="referees",
            field=models.TextField(
                blank=True,
                help_text="Names, positions and contact details of referees (2–3 recommended)",
            ),
        ),
        # Update highest_qualification choices to include WASSCE separately
        migrations.AlterField(
            model_name="jobapplication",
            name="highest_qualification",
            field=models.CharField(
                choices=[
                    ("wassce", "WASSCE"),
                    ("ssce", "SSCE"),
                    ("diploma", "Diploma / HND"),
                    ("degree", "Bachelor's Degree"),
                    ("masters", "Master's Degree"),
                    ("phd", "PhD / Doctorate"),
                    ("professional", "Professional Certificate"),
                    ("other", "Other"),
                ],
                default="degree",
                max_length=20,
            ),
        ),
    ]
