from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0022_alter_fee_managers_alter_feestructure_managers_and_more"),
        ("schools", "0013_paystack_status_length"),
    ]

    operations = [
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
        migrations.AddField(
            model_name="feepayment",
            name="paid_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Set when status transitions to completed.",
            ),
        ),
        migrations.RunSQL(
            sql="""
                UPDATE finance_feepayment
                SET school_id = (
                    SELECT f.school_id FROM finance_fee f WHERE f.id = finance_feepayment.fee_id
                )
                WHERE school_id IS NULL;

                UPDATE finance_feepayment
                SET paid_at = created_at
                WHERE status = 'completed' AND paid_at IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
