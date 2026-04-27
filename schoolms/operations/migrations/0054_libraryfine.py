"""
Add LibraryFine model for tracking overdue book fines with partial payment
and waiver support.
"""
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0053_buspayment_partial_and_ledger'),
        ('schools', '0015_school_timezone_email_branding'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LibraryFine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fine_amount', models.DecimalField(
                    decimal_places=2,
                    max_digits=8,
                    help_text='Total fine charged (days_overdue × fine_per_day).',
                )),
                ('amount_paid', models.DecimalField(
                    decimal_places=2,
                    default=Decimal('0'),
                    max_digits=8,
                )),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('partial', 'Partially Paid'),
                        ('paid', 'Paid'),
                        ('waived', 'Waived'),
                    ],
                    default='pending',
                    max_length=10,
                )),
                ('waiver_reason', models.CharField(blank=True, max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('school', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='library_fines',
                    to='schools.school',
                )),
                ('issue', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fine',
                    to='operations.libraryissue',
                    help_text='Borrowing record this fine is attached to.',
                )),
                ('waived_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='waived_library_fines',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='libraryfine',
            index=models.Index(fields=['school', 'status'], name='idx_libfine_school_status'),
        ),
        migrations.AddConstraint(
            model_name='libraryfine',
            constraint=models.CheckConstraint(
                check=models.Q(fine_amount__gte=0),
                name='chk_libfine_amount_nonneg',
            ),
        ),
        migrations.AddConstraint(
            model_name='libraryfine',
            constraint=models.CheckConstraint(
                check=models.Q(amount_paid__gte=0),
                name='chk_libfine_paid_nonneg',
            ),
        ),
    ]
