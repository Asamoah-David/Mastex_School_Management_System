# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0002_school_address_school_email_school_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='logo_url',
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='school',
            name='academic_year',
            field=models.CharField(blank=True, max_length=50),
        ),
    ]
