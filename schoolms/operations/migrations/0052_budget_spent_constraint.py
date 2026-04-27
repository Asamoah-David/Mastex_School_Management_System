"""
Add Budget.spent_amount CheckConstraint (non-negative).
The auto-sync signal is registered in operations/models/finance.py and
requires no migration — signals are wired at app startup.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0051_hostelfee_term_fk'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='budget',
            constraint=models.CheckConstraint(
                check=models.Q(spent_amount__gte=0),
                name='chk_budget_spent_nonneg',
            ),
        ),
    ]
