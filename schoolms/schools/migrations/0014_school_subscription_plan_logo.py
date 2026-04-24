from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0013_paystack_status_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="subscription_plan",
            field=models.CharField(
                choices=[("basic", "Basic"), ("standard", "Standard"), ("premium", "Premium")],
                default="basic",
                help_text="Feature tier for this school's subscription.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="logo",
            field=models.ImageField(
                blank=True,
                help_text="Upload school logo (PNG/JPG). Takes precedence over logo_url if set.",
                null=True,
                upload_to="school_logos/%Y/",
            ),
        ),
    ]
