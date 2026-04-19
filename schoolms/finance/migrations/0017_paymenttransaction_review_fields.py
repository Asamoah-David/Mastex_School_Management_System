from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0016_paymenttransaction_provider_choices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="paymenttransaction",
            name="review_status",
            field=models.CharField(
                choices=[("open", "Open"), ("reviewed", "Reviewed")],
                db_index=True,
                default="open",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_payment_transactions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
