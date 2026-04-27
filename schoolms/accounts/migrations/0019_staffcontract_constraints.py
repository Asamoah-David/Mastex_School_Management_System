"""
Add DB-level constraints to StaffContract:
 - Prevent two 'active' contracts for the same school + user.
 - Enforce end_date > start_date when end_date is set.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_user_phone_unique'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='staffcontract',
            constraint=models.UniqueConstraint(
                fields=['school', 'user'],
                condition=models.Q(status='active'),
                name='uniq_staffcontract_one_active_per_school_user',
            ),
        ),
        migrations.AddConstraint(
            model_name='staffcontract',
            constraint=models.CheckConstraint(
                check=models.Q(end_date__isnull=True) | models.Q(end_date__gt=models.F('start_date')),
                name='chk_staffcontract_end_after_start',
            ),
        ),
    ]
