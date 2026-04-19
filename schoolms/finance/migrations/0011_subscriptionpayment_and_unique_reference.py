from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0010_alter_feepayment_payer_notified_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Net amount credited to the platform subscription (excluding processing uplift).",
                        max_digits=12,
                    ),
                ),
                (
                    "gross_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Total charged on Paystack (includes uplift when pass-fee-to-payer is on).",
                        max_digits=12,
                        null=True,
                    ),
                ),
                ("paystack_payment_id", models.CharField(blank=True, max_length=255, null=True)),
                ("paystack_reference", models.CharField(db_index=True, max_length=255)),
                ("payment_method", models.CharField(blank=True, max_length=50)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed")],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscription_payments",
                        to="schools.school",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subscription_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Subscription Payment",
                "verbose_name_plural": "Subscription Payments",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="feepayment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("paystack_reference__isnull", False)),
                fields=("paystack_reference",),
                name="uniq_feepayment_paystack_reference_nonnull",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscriptionpayment",
            constraint=models.UniqueConstraint(
                fields=("paystack_reference",),
                name="uniq_subscriptionpayment_paystack_reference",
            ),
        ),
    ]
