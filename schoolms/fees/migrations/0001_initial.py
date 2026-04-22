import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('finance', '0001_initial'),
        ('schools', '0001_initial'),
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('description', models.TextField(blank=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('duration_days', models.IntegerField(help_text='Duration in days')),
                ('max_students', models.IntegerField(default=100)),
                ('max_staff', models.IntegerField(default=10)),
                ('features', models.JSONField(blank=True, default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='SchoolSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled')], default='active', max_length=20)),
                ('expires_at', models.DateTimeField()),
                ('auto_renew', models.BooleanField(default=True)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='fees.subscriptionplan')),
                ('school', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to='schools.school')),
            ],
        ),
        migrations.CreateModel(
            name='PaymentReminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reminder_type', models.CharField(choices=[('due', 'Due'), ('overdue', 'Overdue'), ('receipt', 'Receipt')], max_length=20)),
                ('reminder_date', models.DateTimeField()),
                ('sent', models.BooleanField(default=False)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('fee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_reminders', to='finance.fee')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_reminders', to='students.student')),
            ],
            options={
                'ordering': ['-reminder_date'],
            },
        ),
    ]
