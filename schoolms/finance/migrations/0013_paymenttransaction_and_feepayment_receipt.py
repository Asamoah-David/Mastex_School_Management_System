from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0012_fee_amount_nonnegative_constraints"),
        ("schools", "0007_remove_school_flutterwave_tx_ref_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="feepayment",
            name="receipt_no",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.CreateModel(
            name="PaymentTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("paystack", "Paystack")], default="paystack", max_length=30)),
                ("reference", models.CharField(db_index=True, max_length=255, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="GHS", max_length=10)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed")], db_index=True, default="pending", max_length=20)),
                ("payment_type", models.CharField(blank=True, default="", max_length=50)),
                ("object_id", models.CharField(blank=True, default="", max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="schools.school")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="paymenttransaction",
            index=models.Index(fields=["school", "created_at"], name="idx_paytx_school_created"),
        ),
        migrations.AddIndex(
            model_name="paymenttransaction",
            index=models.Index(fields=["provider", "status"], name="idx_paytx_provider_status"),
        ),
    ]
