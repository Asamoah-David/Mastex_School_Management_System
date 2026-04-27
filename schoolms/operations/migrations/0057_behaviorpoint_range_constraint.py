"""
Fix #39: Add CheckConstraint on BehaviorPoint.points to enforce -100..100.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0056_budget_academic_year_term_fk"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="behaviorpoint",
            constraint=models.CheckConstraint(
                check=models.Q(points__gte=-100) & models.Q(points__lte=100),
                name="points_within_range",
            ),
        ),
    ]
