from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0004_rename_idx_gdpr_school_status_audit_gdpre_school__316598_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='gdprexportrequest',
            name='export_payload',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Serialised personal-data dict; served as a FileResponse download.',
            ),
        ),
    ]
