from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0029_approvalworkflow_fixedasset_workflowinstance_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='fixedasset',
            name='currency',
            field=models.CharField(
                default='GHS',
                help_text='Purchase / valuation currency (ISO-4217). Inherited from school.currency by default.',
                max_length=8,
            ),
        ),
    ]
