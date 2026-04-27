"""
Add gross-to-net payroll deduction fields to StaffPayrollPayment:
  - gross_amount: gross salary before deductions
  - net_amount: take-home after deductions (mirrors amount when using the payroll engine)
  - deductions_breakdown: JSON snapshot of PAYE, SSNIT, etc.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0020_passwordresetrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffpayrollpayment',
            name='gross_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Gross salary before statutory deductions (PAYE, SSNIT). Populated by payroll engine.',
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='staffpayrollpayment',
            name='net_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Net take-home after all deductions. Should equal amount when using the payroll engine.',
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='staffpayrollpayment',
            name='deductions_breakdown',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Gross-to-net breakdown: ssnit_employee, paye, total_deductions, etc.',
            ),
        ),
        migrations.AlterField(
            model_name='staffpayrollpayment',
            name='amount',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                help_text='Amount actually disbursed (net pay).',
            ),
        ),
    ]
