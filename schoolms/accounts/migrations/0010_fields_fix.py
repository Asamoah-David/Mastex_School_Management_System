# Generated migration for field alterations (gender field already exists)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_alter_profile_photo_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='failed_login_attempts',
            field=models.PositiveIntegerField(default=0, help_text='Number of consecutive failed login attempts'),
        ),
        migrations.AlterField(
            model_name='user',
            name='last_failed_login',
            field=models.DateTimeField(blank=True, help_text='Timestamp of last failed login attempt', null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='lockout_until',
            field=models.DateTimeField(blank=True, help_text='Timestamp when account lockout expires', null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='profile_photo',
            field=models.ImageField(blank=True, null=True, upload_to='profile_photos/'),
        ),
    ]
