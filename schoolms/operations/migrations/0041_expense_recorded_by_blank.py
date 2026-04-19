from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0040_textbooksale_recorded_by_blank"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expense",
            name="recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="recorded_expenses",
                to="accounts.user",
            ),
        ),
    ]
