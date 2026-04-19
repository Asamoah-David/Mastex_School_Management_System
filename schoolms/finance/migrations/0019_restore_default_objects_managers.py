import django.db.models.manager
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0018_alter_fee_managers_alter_feestructure_managers_and_more"),
    ]

    operations = [
        migrations.AlterModelManagers(
            name="fee",
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("scoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AlterModelManagers(
            name="feestructure",
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("scoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AlterModelManagers(
            name="subscriptionpayment",
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("scoped", django.db.models.manager.Manager()),
            ],
        ),
    ]
