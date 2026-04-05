# Generated migration to add missing Result fields and fix Timetable

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0009_alter_gradingpolicy_unique_together'),
    ]

    operations = [
        # Rename day to day_of_week in Timetable
        migrations.RenameField(
            model_name='timetable',
            old_name='day',
            new_name='day_of_week',
        ),
        # Add missing fields to Result model
        migrations.AddField(
            model_name='result',
            name='created_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.user'),
        ),
        migrations.AddField(
            model_name='result',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=None),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='result',
            name='remarks',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='result',
            name='subject',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='academics.subject'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='result',
            name='student',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='students.student'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='result',
            name='total_score',
            field=models.FloatField(default=100),
        ),
        migrations.AddField(
            model_name='result',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
