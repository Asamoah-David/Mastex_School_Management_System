# Generated manually for expanded role system

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_user_assigned_subjects'),
    ]

    operations = [
        # This migration documents the new roles but doesn't change the database
        # The new roles are just string values in the existing role field
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('super_admin', 'Super Admin'),
                    ('school_admin', 'Headteacher/Admin'),
                    ('deputy_head', 'Deputy Headteacher'),
                    ('hod', 'Head of Department'),
                    ('teacher', 'Teacher'),
                    ('accountant', 'Accountant/Bursar'),
                    ('librarian', 'Librarian'),
                    ('admission_officer', 'Admission Officer'),
                    ('school_nurse', 'School Nurse'),
                    ('admin_assistant', 'Admin Assistant'),
                    ('staff', 'Staff'),
                    ('student', 'Student'),
                    ('parent', 'Parent'),
                ],
                default='parent',
                max_length=20,
            ),
        ),
    ]
