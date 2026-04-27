"""
Add StudentGuardian through-table: supports multiple parents/guardians per student.
The legacy Student.parent FK is preserved for backward compatibility.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0015_unique_student_admission_number_per_school'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentGuardian',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('relationship', models.CharField(
                    choices=[
                        ('father', 'Father'),
                        ('mother', 'Mother'),
                        ('guardian', 'Guardian'),
                        ('step_parent', 'Step Parent'),
                        ('grandparent', 'Grandparent'),
                        ('sibling', 'Sibling'),
                        ('other', 'Other'),
                    ],
                    default='guardian',
                    max_length=20,
                )),
                ('is_primary', models.BooleanField(
                    default=False,
                    help_text='Primary guardian receives all notifications and fee alerts.',
                )),
                ('can_pickup', models.BooleanField(
                    default=True,
                    help_text='Authorised to collect student from school.',
                )),
                ('emergency_contact', models.BooleanField(
                    default=False,
                    help_text='Listed as emergency contact.',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('guardian', models.ForeignKey(
                    limit_choices_to={'role': 'parent'},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ward_relationships',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='guardians',
                    to='students.student',
                )),
            ],
            options={
                'verbose_name': 'Student Guardian',
                'verbose_name_plural': 'Student Guardians',
            },
        ),
        migrations.AlterUniqueTogether(
            name='studentguardian',
            unique_together={('student', 'guardian')},
        ),
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(fields=['guardian'], name='idx_stuguardian_guardian'),
        ),
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(fields=['student', 'is_primary'], name='idx_stuguardian_primary'),
        ),
        migrations.AddConstraint(
            model_name='studentguardian',
            constraint=models.UniqueConstraint(
                condition=models.Q(is_primary=True),
                fields=['student'],
                name='uniq_stuguardian_one_primary_per_student',
            ),
        ),
    ]
