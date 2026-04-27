"""
BusPayment partial payment support:
 - Add amount_paid, payment_history fields
 - Add CheckConstraint on amount_paid
 - Create BusPaymentLedger immutable table
"""
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0052_budget_spent_constraint'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # BusPayment: add amount_paid
        migrations.AddField(
            model_name='buspayment',
            name='amount_paid',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Running total of partial payments credited so far.',
                max_digits=10,
            ),
        ),
        # BusPayment: add payment_history JSON
        migrations.AddField(
            model_name='buspayment',
            name='payment_history',
            field=models.JSONField(blank=True, default=list),
        ),
        # BusPayment: CheckConstraint
        migrations.AddConstraint(
            model_name='buspayment',
            constraint=models.CheckConstraint(
                check=models.Q(amount_paid__gte=0),
                name='chk_buspayment_amount_paid_nonneg',
            ),
        ),
        # BusPaymentLedger immutable rows
        migrations.CreateModel(
            name='BusPaymentLedger',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_reference', models.CharField(blank=True, db_index=True, default='', max_length=100)),
                ('payment_date', models.DateTimeField(auto_now_add=True)),
                ('bus_payment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ledger_entries',
                    to='operations.buspayment',
                )),
                ('recorded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-payment_date', '-id']},
        ),
        migrations.AddConstraint(
            model_name='buspaymentledger',
            constraint=models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='chk_buspayledger_amount_positive',
            ),
        ),
    ]
