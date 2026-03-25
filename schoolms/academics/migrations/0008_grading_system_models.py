# Generated migration for new grading system models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0007_homework_attachment'),
        ('students', '0007_add_quiz_and_term_dates'),
        ('schools', '0006_school_subscription_amount'),
    ]

    operations = [
        # AssessmentType model
        migrations.CreateModel(
            name='AssessmentType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
            ],
            options={
                'verbose_name_plural': 'Assessment Types',
                'ordering': ['name'],
            },
        ),
        
        # GradingPolicy model
        migrations.CreateModel(
            name='GradingPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Default Policy', max_length=100)),
                ('ca_weight', models.FloatField(default=50.0)),
                ('exam_weight', models.FloatField(default=50.0)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
            ],
        ),
        
        # GradePoint model
        migrations.CreateModel(
            name='GradePoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grade', models.CharField(choices=[('A+', 'A+'), ('A', 'A'), ('A-', 'A-'), ('B+', 'B+'), ('B', 'B'), ('B-', 'B-'), ('C+', 'C+'), ('C', 'C'), ('C-', 'C-'), ('D+', 'D+'), ('D', 'D'), ('D-', 'D-'), ('F', 'F')], max_length=5)),
                ('min_score', models.FloatField()),
                ('max_score', models.FloatField()),
                ('point_value', models.FloatField()),
                ('scale', models.CharField(choices=[('5.0', '5.0 Scale'), ('4.0', '4.0 Scale')], default='5.0', max_length=5)),
                ('is_default', models.BooleanField(default=False)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
            ],
            options={
                'ordering': ['-min_score'],
                'unique_together': {('school', 'grade', 'scale')},
            },
        ),
        
        # AssessmentScore model
        migrations.CreateModel(
            name='AssessmentScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.FloatField()),
                ('max_score', models.FloatField(default=100.0)),
                ('date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assessment_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.assessmenttype')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='students.student')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.subject')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.term')),
            ],
            options={
                'ordering': ['-date'],
                'verbose_name': 'Assessment Score',
                'verbose_name_plural': 'Assessment Scores',
            },
        ),
        
        # ExamScore model
        migrations.CreateModel(
            name='ExamScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.FloatField()),
                ('max_score', models.FloatField(default=100.0)),
                ('date', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('exam_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='academics.examtype')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='students.student')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.subject')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.term')),
            ],
            options={
                'verbose_name': 'Exam Score',
                'verbose_name_plural': 'Exam Scores',
                'unique_together': {('student', 'subject', 'term')},
            },
        ),
        
        # StudentResultSummary model
        migrations.CreateModel(
            name='StudentResultSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ca_score', models.FloatField(default=0)),
                ('exam_score', models.FloatField(default=0)),
                ('final_score', models.FloatField(default=0)),
                ('grade', models.CharField(blank=True, max_length=5)),
                ('grade_point', models.FloatField(default=0)),
                ('term_position', models.PositiveIntegerField(blank=True, null=True)),
                ('cumulative_position', models.PositiveIntegerField(blank=True, null=True)),
                ('gpa', models.FloatField(default=0)),
                ('cumulative_gpa', models.FloatField(default=0)),
                ('calculated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='students.student')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.subject')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.term')),
            ],
            options={
                'ordering': ['term', 'student'],
                'verbose_name': 'Student Result Summary',
                'verbose_name_plural': 'Student Result Summaries',
                'unique_together': {('student', 'subject', 'term')},
            },
        ),
    ]
