from django.db import migrations, models


def _backfill_active_status(apps, schema_editor):
    School = apps.get_model("schools", "School")
    School.objects.exclude(paystack_subaccount_code__isnull=True).exclude(
        paystack_subaccount_code=""
    ).update(paystack_subaccount_status="active")


def _noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0011_erp_enhancements_batch1"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="paystack_bank_code",
            field=models.CharField(
                blank=True,
                help_text="Paystack bank code (from list_banks)",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="paystack_subaccount_status",
            field=models.CharField(
                choices=[
                    ("inactive", "Not set up"),
                    ("pending", "Pending verification"),
                    ("active", "Active"),
                    ("failed", "Failed"),
                ],
                default="inactive",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="paystack_subaccount_last_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="school",
            name="paystack_subaccount_last_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="school",
            name="paystack_subaccount_code",
            field=models.CharField(
                blank=True,
                help_text="Paystack subaccount code (created automatically)",
                max_length=100,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_active_status, _noop_reverse),
    ]
