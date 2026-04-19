from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0014_paymenttransaction_school_status_created_idx"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="paymenttransaction",
            index=models.Index(
                fields=["school", "payment_type", "created_at"],
                name="idx_paytx_school_type_created",
            ),
        ),
    ]
