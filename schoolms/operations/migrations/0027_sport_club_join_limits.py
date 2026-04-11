from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0026_schoolevent_choices_and_properties"),
    ]

    operations = [
        migrations.AddField(
            model_name="sport",
            name="max_members",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Maximum approved roster size. Leave empty for no limit.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="sport",
            name="join_requires_approval",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, student self-joins wait for coach or leadership approval.",
            ),
        ),
        migrations.AddField(
            model_name="club",
            name="max_members",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Maximum approved members. Leave empty for no limit.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="club",
            name="join_requires_approval",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, student self-joins wait for sponsor or leadership approval.",
            ),
        ),
        migrations.AddField(
            model_name="studentsport",
            name="pending_approval",
            field=models.BooleanField(
                default=False,
                help_text="True when the student requested to join and is awaiting approval.",
            ),
        ),
        migrations.AddField(
            model_name="studentclub",
            name="pending_approval",
            field=models.BooleanField(
                default=False,
                help_text="True when the student requested to join and is awaiting approval.",
            ),
        ),
    ]
