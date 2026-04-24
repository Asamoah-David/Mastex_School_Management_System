"""
Fix 1: Enforce phone-number uniqueness at the DB level.

A partial UniqueConstraint is used so that:
 - NULL phones are exempt (multiple users with no phone are fine).
 - Empty-string phones are exempt (legacy rows without a phone).
 - Only non-empty phone numbers must be globally unique.

This prevents the SMS OTP reset from matching multiple accounts and
ensures each phone maps to exactly one active user.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_staffcontract_salary_teachingassignment_class"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=["phone"],
                condition=models.Q(phone__isnull=False) & ~models.Q(phone=""),
                name="uniq_user_phone_nonempty",
            ),
        ),
    ]
