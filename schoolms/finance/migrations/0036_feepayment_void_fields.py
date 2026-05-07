# Fee payment void / reversal tracking

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0035_feepayment_school_status_created_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="feepayment",
            name="voided_at",
            field=models.DateTimeField(blank=True, db_index=True, help_text="When set, this payment is voided; fee balance is reduced (reversal workflow).", null=True),
        ),
        migrations.AddField(
            model_name="feepayment",
            name="void_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="feepayment",
            name="voided_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fee_payments_voided", to=settings.AUTH_USER_MODEL),
        ),
    ]
