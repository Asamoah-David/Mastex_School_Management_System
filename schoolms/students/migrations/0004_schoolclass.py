# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0002_school_address_school_email_school_phone'),
        ('accounts', '0004_alter_user_role'),
        ('students', '0003_student_allergies_student_blood_group_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SchoolClass',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('capacity', models.PositiveIntegerField(blank=True, default=40, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('class_teacher', models.ForeignKey(blank=True, limit_choices_to={'role__in': ['admin', 'teacher']}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='classes_taught', to='accounts.user')),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
            ],
            options={
                'ordering': ['name'],
                'verbose_name': 'Class',
                'verbose_name_plural': 'Classes',
                'unique_together': {('school', 'name')},
            },
        ),
    ]
