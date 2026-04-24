"""
Fix 24: Add School.timezone field.
Fix 23: Add SchoolEmailBranding model for per-school email customisation.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0014_school_subscription_plan_logo"),
    ]

    operations = [
        # Fix 24: timezone field
        migrations.AddField(
            model_name="school",
            name="timezone",
            field=models.CharField(
                default="Africa/Accra",
                help_text="IANA timezone (e.g. Africa/Accra, Africa/Lagos, Africa/Nairobi).",
                max_length=50,
            ),
        ),
        # Fix 23: SchoolEmailBranding
        migrations.CreateModel(
            name="SchoolEmailBranding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "school",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_branding",
                        to="schools.school",
                    ),
                ),
                (
                    "header_color",
                    models.CharField(
                        default="#1a73e8",
                        help_text="Hex colour for email header background (e.g. #1a73e8).",
                        max_length=20,
                    ),
                ),
                (
                    "logo_override_url",
                    models.URLField(
                        blank=True,
                        help_text="If set, overrides the school logo in emails.",
                        max_length=500,
                    ),
                ),
                (
                    "footer_text",
                    models.TextField(
                        blank=True,
                        help_text="Custom footer for all outbound emails (HTML allowed).",
                    ),
                ),
                (
                    "reply_to_email",
                    models.EmailField(
                        blank=True,
                        help_text="Reply-to address for all outbound emails. Defaults to school.email.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "School Email Branding",
                "verbose_name_plural": "School Email Branding",
            },
        ),
    ]
