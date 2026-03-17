from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0004_announcement_staffleave_activitylog"),
    ]

    operations = [
        migrations.AlterField(
            model_name="librarybook",
            name="isbn",
            field=models.CharField(max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name="librarybook",
            unique_together={("school", "isbn")},
        ),
    ]

