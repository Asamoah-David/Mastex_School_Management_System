from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0012_school_payout_setup_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="school",
            name="paystack_subaccount_status",
            field=models.CharField(
                max_length=32,
                choices=[
                    ("inactive", "Not set up"),
                    ("pending", "Pending verification"),
                    ("active", "Active"),
                    ("failed", "Failed"),
                    ("unsupported_bank", "Unsupported bank"),
                    ("pending_manual_review", "Pending manual review"),
                ],
                default="inactive",
            ),
        ),
    ]
