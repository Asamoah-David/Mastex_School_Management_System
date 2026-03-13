from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0004_gradeboundary_homework_examschedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="examschedule",
            name="class_name",
            field=models.CharField(max_length=100, blank=True),
        ),
    ]

