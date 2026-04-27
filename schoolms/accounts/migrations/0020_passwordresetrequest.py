"""
Add PasswordResetRequest model for rate-limiting and auditing password reset flows.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0019_staffcontract_constraints'),
    ]

    operations = [
        migrations.CreateModel(
            name='PasswordResetRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(
                    help_text='Email address the reset was requested for (snapshot at request time).',
                    max_length=254,
                )),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(
                    help_text='When the token expires (typically 1 hour).',
                )),
                ('used_at', models.DateTimeField(
                    blank=True,
                    null=True,
                    help_text='Timestamp when the reset link was consumed. Null = not yet used.',
                )),
                ('user', models.ForeignKey(
                    blank=True,
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='password_reset_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Password Reset Request',
                'verbose_name_plural': 'Password Reset Requests',
                'ordering': ['-requested_at'],
            },
        ),
        migrations.AddIndex(
            model_name='passwordresetrequest',
            index=models.Index(
                fields=['email', 'requested_at'],
                name='idx_pwreset_email_requested',
            ),
        ),
        migrations.AddIndex(
            model_name='passwordresetrequest',
            index=models.Index(
                fields=['ip_address', 'requested_at'],
                name='idx_pwreset_ip_requested',
            ),
        ),
    ]
