import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0002_ai_school_scoping'),
        ('schools', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SchoolMonthlyTokenUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveSmallIntegerField()),
                ('month', models.PositiveSmallIntegerField()),
                ('tokens_used', models.PositiveBigIntegerField(default=0)),
                ('school', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='monthly_token_usage',
                    to='schools.school',
                )),
            ],
            options={
                'unique_together': {('school', 'year', 'month')},
            },
        ),
        migrations.AddIndex(
            model_name='schoolmonthlytokenusage',
            index=models.Index(fields=['school', 'year', 'month'], name='idx_tokusage_school_ym'),
        ),
    ]
