from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0037_alter_studentdocument_managers_expense_approved_at_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HostelFeePayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("payment_reference", models.CharField(blank=True, db_index=True, default="", max_length=100)),
                ("payment_date", models.DateTimeField(auto_now_add=True)),
                (
                    "hostel_fee",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payment_entries", to="operations.hostelfee"),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "ordering": ["-payment_date", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="hostelfeepayment",
            index=models.Index(fields=["hostel_fee", "payment_date"], name="idx_hostelfeepay_fee_date"),
        ),
        migrations.AddConstraint(
            model_name="hostelfeepayment",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="chk_hostelfeepay_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="hostelfeepayment",
            constraint=models.UniqueConstraint(condition=~models.Q(("payment_reference", "")), fields=("payment_reference",), name="uniq_hostelfeepay_reference_nonempty"),
        ),
    ]
