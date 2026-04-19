from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0038_hostelfeepayment_ledger"),
    ]

    operations = [
        migrations.AlterField(
            model_name="canteenpayment",
            name="recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="canteen_payments_recorded",
                to="accounts.user",
            ),
        ),
    ]
