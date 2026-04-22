from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0023_result_publish_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="timetable",
            name="teacher",
            field=models.ForeignKey(
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
                related_name="timetable_subjects",
                to="accounts.user",
            ),
        ),
    ]
