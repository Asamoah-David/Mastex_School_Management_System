# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0002_school_address_school_email_school_phone'),
        ('academics', '0003_examtype_result_exam_type_term_result_term'),
        ('accounts', '0004_alter_user_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='GradeBoundary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grade', models.CharField(max_length=5)),
                ('min_score', models.FloatField()),
                ('max_score', models.FloatField()),
                ('order', models.PositiveIntegerField(default=0)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
            ],
            options={
                'ordering': ['-min_score'],
                'unique_together': {('school', 'grade')},
            },
        ),
        migrations.CreateModel(
            name='Homework',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('class_name', models.CharField(max_length=100)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('due_date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='homework_created', to='accounts.user')),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.subject')),
            ],
            options={
                'ordering': ['-due_date'],
            },
        ),
        migrations.CreateModel(
            name='ExamSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exam_date', models.DateField()),
                ('start_time', models.TimeField(blank=True, null=True)),
                ('end_time', models.TimeField(blank=True, null=True)),
                ('room', models.CharField(blank=True, max_length=50)),
                ('notes', models.TextField(blank=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.subject')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.term')),
            ],
            options={
                'ordering': ['exam_date', 'start_time'],
            },
        ),
    ]
