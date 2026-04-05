# Generated manually to add missing target_audience field to OnlineMeeting

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0011_alter_studentresultsummary_unique_together_and_more'),
    ]

    operations = [
        # Add target_audience field to OnlineMeeting (class_name already exists in some databases)
        migrations.AddField(
            model_name='onlinemeeting',
            name='target_audience',
            field=models.CharField(choices=[('students', 'Students Only'), ('staff', 'Staff Only'), ('all', 'All Users')], default='all', max_length=20),
        ),
    ]
