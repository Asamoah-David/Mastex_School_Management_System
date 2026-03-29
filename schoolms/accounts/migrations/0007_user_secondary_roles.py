# Updated migration for secondary roles as TextField

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_update_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='secondary_roles',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Comma-separated list of secondary role values'
            ),
        ),
        # Also add login rate limiting fields at the same step
        migrations.AddField(
            model_name='user',
            name='failed_login_attempts',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='user',
            name='last_failed_login',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='lockout_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]