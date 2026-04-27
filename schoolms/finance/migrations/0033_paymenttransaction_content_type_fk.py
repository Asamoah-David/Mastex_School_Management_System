from django.db import migrations, models
import django.db.models.deletion


_PAYMENT_TYPE_MODEL_MAP = {
    "school_fee":         ("finance",    "fee"),
    "school_fee_manual":  ("finance",    "fee"),
    "school_fee_offline": ("finance",    "fee"),
    "canteen":            ("operations", "canteenpayment"),
    "bus":                ("operations", "buspayment"),
    "textbook":           ("operations", "textbooksale"),
    "hostel":             ("operations", "hostelfee"),
}


def _backfill_content_types(apps, schema_editor):
    PaymentTransaction = apps.get_model("finance", "PaymentTransaction")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct_cache = {}
    for pt, (app_label, model) in _PAYMENT_TYPE_MODEL_MAP.items():
        try:
            ct_cache[pt] = ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            ct_cache[pt] = None

    to_update = []
    for tx in PaymentTransaction.objects.filter(
        content_type__isnull=True,
        payment_type__in=list(_PAYMENT_TYPE_MODEL_MAP.keys()),
    ).only("pk", "payment_type"):
        ct = ct_cache.get(tx.payment_type)
        if ct:
            tx.content_type = ct
            to_update.append(tx)
        if len(to_update) >= 500:
            PaymentTransaction.objects.bulk_update(to_update, ["content_type"])
            to_update = []
    if to_update:
        PaymentTransaction.objects.bulk_update(to_update, ["content_type"])


class Migration(migrations.Migration):
    """DB-4: Add content_type FK + GenericForeignKey to PaymentTransaction.

    The existing payment_type / object_id fields are retained for backward
    compatibility. content_type is back-filled from payment_type via RunPython.
    """

    dependencies = [
        ("finance", "0032_feediscount_workflowinstance_steps_snapshot"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymenttransaction",
            name="content_type",
            field=models.ForeignKey(
                blank=True,
                help_text="ContentType of the payment subject (Fee, CanteenPayment, BusPayment, etc.). Used with object_id to form a GenericForeignKey.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="contenttypes.ContentType",
            ),
        ),
        migrations.RunPython(
            _backfill_content_types,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddIndex(
            model_name="paymenttransaction",
            index=models.Index(
                fields=["content_type", "object_id"],
                name="idx_paytx_ct_obj",
            ),
        ),
    ]
