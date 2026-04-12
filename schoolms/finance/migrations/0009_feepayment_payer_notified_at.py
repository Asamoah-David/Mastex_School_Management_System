# Generated manually for fee payment notification deduplication (callback vs webhook).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_fee_payment_gross_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="feepayment",
            name="payer_notified_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When parent/student SMS+email notices were sent (avoids duplicates if callback and webhook both run).",
            ),
        ),
    ]
