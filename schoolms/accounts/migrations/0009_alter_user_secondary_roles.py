# Migration to change secondary_roles from ManyToMany to TextField

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_user_profile_photo'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='secondary_roles',
        ),
        migrations.AddField(
            model_name='user',
            name='secondary_roles',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Comma-separated list of secondary role values'
            ),
        ),
    ]