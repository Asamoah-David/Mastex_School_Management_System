"""
Fix #2: SchoolFeature cache signals (Python-only, no DB change).
Fix #23: Plan feature tier enforcement (Python-only).
Fix #29: SchoolNetwork model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0016_school_ai_monthly_token_cap"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolNetwork",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("owner_email", models.EmailField(blank=True)),
                ("logo_url", models.URLField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("schools", models.ManyToManyField(
                    blank=True,
                    help_text="Schools that belong to this network.",
                    related_name="networks",
                    to="schools.school",
                )),
            ],
            options={
                "verbose_name": "School Network",
                "verbose_name_plural": "School Networks",
                "ordering": ["name"],
            },
        ),
    ]
