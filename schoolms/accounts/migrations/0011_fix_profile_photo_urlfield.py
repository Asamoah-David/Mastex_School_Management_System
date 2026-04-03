# Migration to fix profile_photo field - change from ImageField to URLField with max_length=500
# This is needed because Supabase URLs are longer than 100 characters

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_fields_fix'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='profile_photo',
            field=models.URLField(max_length=500, null=True, blank=True),
        ),
    ]
