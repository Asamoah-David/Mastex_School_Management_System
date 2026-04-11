# Generated manually

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("students", "0013_alter_schoolclass_class_teacher"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentClearance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fees_cleared", models.BooleanField(default=False)),
                ("library_cleared", models.BooleanField(default=False)),
                ("id_card_returned", models.BooleanField(default=False)),
                ("discipline_cleared", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "student",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clearance_record",
                        to="students.student",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Student clearance",
                "verbose_name_plural": "Student clearances",
            },
        ),
    ]
