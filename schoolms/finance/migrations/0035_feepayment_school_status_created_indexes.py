# Generated manually for finance dashboards and payment history queries.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0034_erp_new_models_batch"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="feepayment",
            index=models.Index(
                fields=["school", "status", "paid_at"],
                name="idx_feepay_school_stat_paidat",
            ),
        ),
        migrations.AddIndex(
            model_name="feepayment",
            index=models.Index(
                fields=["school", "created_at"],
                name="idx_feepay_school_created",
            ),
        ),
    ]
