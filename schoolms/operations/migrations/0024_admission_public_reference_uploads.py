# Generated manually for AdmissionApplication.public_reference and uploads

import django.core.validators
from django.db import migrations, models


def backfill_public_reference(apps, schema_editor):
    AdmissionApplication = apps.get_model("operations", "AdmissionApplication")
    for row in AdmissionApplication.objects.filter(public_reference__isnull=True).iterator():
        row.public_reference = f"ADM-L{row.pk}"
        row.save(update_fields=["public_reference"])


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0023_examanswer_teacher_reviewed"),
    ]

    operations = [
        migrations.AddField(
            model_name="admissionapplication",
            name="public_reference",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Shown to applicant for status tracking (not secret; do not use as password).",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="admissionapplication",
            name="birth_certificate",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="admission_docs/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["pdf", "jpg", "jpeg", "png", "webp"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="admissionapplication",
            name="previous_report",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="admission_docs/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["pdf", "jpg", "jpeg", "png", "webp"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="admissionapplication",
            name="passport_photo",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="admission_photos/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"]
                    )
                ],
            ),
        ),
        migrations.RunPython(backfill_public_reference, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="admissionapplication",
            name="public_reference",
            field=models.CharField(
                db_index=True,
                help_text="Shown to applicant for status tracking (not secret; do not use as password).",
                max_length=20,
                unique=True,
            ),
        ),
    ]
