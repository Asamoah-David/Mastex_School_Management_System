from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0011_subscriptionpayment_and_unique_reference"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="fee",
            constraint=models.CheckConstraint(
                check=Q(amount__gte=0),
                name="chk_fee_amount_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="fee",
            constraint=models.CheckConstraint(
                check=Q(amount_paid__gte=0),
                name="chk_fee_amount_paid_nonnegative",
            ),
        ),
    ]
