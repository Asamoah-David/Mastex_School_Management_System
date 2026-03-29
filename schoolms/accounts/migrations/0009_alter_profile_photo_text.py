# Generated manually for Mastex SchoolOS

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_user_profile_photo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='profile_photo',
            field=models.URLField(max_length=500, null=True, blank=True),
        ),
    ]
