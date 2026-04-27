from django.db import migrations, models


class Migration(migrations.Migration):
    """BIZ-5: Add steps_snapshot to WorkflowInstance.

    FeeDiscount (BIZ-9) already existed in the codebase — no CreateModel needed.
    """

    dependencies = [
        ("finance", "0031_workflowinstance_generic_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowinstance",
            name="steps_snapshot",
            field=models.JSONField(
                default=list,
                help_text=(
                    "Frozen copy of workflow.steps at the time this instance was created. "
                    "advance() uses this so edits to the parent workflow never corrupt in-flight approvals."
                ),
            ),
        ),
    ]
