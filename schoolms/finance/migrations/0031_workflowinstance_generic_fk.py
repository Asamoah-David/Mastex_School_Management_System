"""
GAP-9/ARCH-1: Replace WorkflowInstance.content_type (CharField) with a real
Django GenericForeignKey via ForeignKey(ContentType).

Steps
-----
1. Rename old CharField to content_type_str (preserve data for the migration).
2. Drop the old composite index that referenced the CharField column.
3. Add new content_type FK (nullable during migration).
4. Data migration: parse content_type_str → ContentType PK.
5. Remove backup field content_type_str.
6. Recreate composite index on the FK column.
"""

import django.db.models.deletion
from django.db import migrations, models


def _populate_content_type_fk(apps, schema_editor):
    """Convert 'app_label.ModelName' strings to real ContentType FKs."""
    WorkflowInstance = apps.get_model('finance', 'WorkflowInstance')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    for inst in WorkflowInstance.objects.all():
        ct_str = (inst.content_type_str or '').strip()
        if not ct_str:
            continue
        # Stored as "app_label.ModelName" — ContentType.model is lowercase
        parts = ct_str.rsplit('.', 1)
        if len(parts) == 2:
            app_label, model_name = parts[0].lower(), parts[1].lower()
            try:
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
                inst.content_type_id = ct.pk
                inst.save(update_fields=['content_type_id'])
            except ContentType.DoesNotExist:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0030_fixedasset_currency'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        # 1 — rename old CharField → backup name
        migrations.RenameField(
            model_name='workflowinstance',
            old_name='content_type',
            new_name='content_type_str',
        ),

        # 2 — drop old index (it referenced the renamed column)
        migrations.RemoveIndex(
            model_name='workflowinstance',
            name='idx_wfinst_ct_obj',
        ),

        # 3 — add new FK (nullable so existing rows survive)
        migrations.AddField(
            model_name='workflowinstance',
            name='content_type',
            field=models.ForeignKey(
                to='contenttypes.ContentType',
                on_delete=django.db.models.deletion.CASCADE,
                null=True,
                help_text='ContentType of the subject model.',
            ),
        ),

        # 4 — populate FK from the string backup
        migrations.RunPython(_populate_content_type_fk, migrations.RunPython.noop),

        # 5 — remove the string backup field
        migrations.RemoveField(
            model_name='workflowinstance',
            name='content_type_str',
        ),

        # 6 — recreate index on the new FK column + object_id
        migrations.AddIndex(
            model_name='workflowinstance',
            index=models.Index(
                fields=['content_type', 'object_id'],
                name='idx_wfinst_ct_obj',
            ),
        ),
    ]
