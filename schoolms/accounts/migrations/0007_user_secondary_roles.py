# Generated manually for secondary roles M2M field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_update_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='secondary_roles',
            field=models.ManyToManyField(
                blank=True,
                related_name='primary_role_of',
                symmetrical=False,
                to='accounts.user'
            ),
        ),
    ]
