# Generated manually to add missing OnlineMeeting fields

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0011_alter_studentresultsummary_unique_together_and_more'),
    ]

    operations = [
        # Add target_audience and class_name fields to OnlineMeeting
        migrations.AddField(
            model_name='onlinemeeting',
            name='target_audience',
            field=models.CharField(choices=[('students', 'Students Only'), ('staff', 'Staff Only'), ('all', 'All Users')], default='all', max_length=20),
        ),
        migrations.AddField(
            model_name='onlinemeeting',
            name='class_name',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
