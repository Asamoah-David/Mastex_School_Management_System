"""
Recovery migration: Clear pending trigger events and re-apply migration 0023 operations.
This resolves the ObjectInUse error on finance_feepayment table index creation.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0022_alter_fee_managers_alter_feestructure_managers_and_more"),
        ("schools", "0013_paystack_status_length"),
    ]

    operations = [
        # Step 1: Clear pending trigger events to unblock index creation
        migrations.RunSQL(
            sql="SET CONSTRAINTS ALL DEFERRED;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 2: Add school ForeignKey field (nullable)
        migrations.AddField(
            model_name="feepayment",
            name="school",
            field=models.ForeignKey(
                blank=True,
                help_text="Denormalised for fast cross-school queries; kept in sync on save.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="schools.school",
            ),
        ),
        # Step 3: Add paid_at DateTimeField
        migrations.AddField(
            model_name="feepayment",
            name="paid_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Set when status transitions to completed.",
            ),
        ),
        # Step 4: Populate school_id from related fee
        migrations.RunSQL(
            sql="""
                UPDATE finance_feepayment
                SET school_id = (
                    SELECT f.school_id FROM finance_fee f WHERE f.id = finance_feepayment.fee_id
                )
                WHERE school_id IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 5: Populate paid_at for completed payments
        migrations.RunSQL(
            sql="""
                UPDATE finance_feepayment
                SET paid_at = created_at
                WHERE status = 'completed' AND paid_at IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 6: Mark migration 0023 as applied since we've replicated its operations
        migrations.RunSQL(
            sql="""
                INSERT INTO django_migrations (app, name, applied)
                VALUES ('finance', '0023_feepayment_school_paid_at', NOW())
                ON CONFLICT (app, name) DO NOTHING;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
