from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0039_canteenpayment_recorded_by_blank"),
    ]

    operations = [
        migrations.AlterField(
            model_name="textbooksale",
            name="recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="textbook_sales_recorded",
                to="accounts.user",
            ),
        ),
    ]
