from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0013_paymenttransaction_and_feepayment_receipt"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="paymenttransaction",
            index=models.Index(
                fields=["school", "status", "created_at"],
                name="idx_paytx_s_st_cr",
            ),
        ),
    ]
