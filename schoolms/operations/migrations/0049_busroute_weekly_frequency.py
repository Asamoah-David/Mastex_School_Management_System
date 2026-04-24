from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0048_remove_admission_legacy_path_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="busroute",
            name="payment_frequency",
            field=models.CharField(
                choices=[("term", "Per Term"), ("weekly", "Weekly"), ("daily", "Daily")],
                default="term",
                max_length=10,
            ),
        ),
    ]
