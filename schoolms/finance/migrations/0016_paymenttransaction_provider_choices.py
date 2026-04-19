from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0015_paymenttransaction_school_type_created_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymenttransaction",
            name="provider",
            field=models.CharField(
                choices=[("paystack", "Paystack"), ("manual", "Manual"), ("offline", "Offline")],
                default="paystack",
                max_length=30,
            ),
        ),
    ]
