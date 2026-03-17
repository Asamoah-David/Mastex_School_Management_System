from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0005_student_status_and_absencerequest"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="absencerequest",
            name="submitted_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Who submitted this request (student or parent).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="absence_requests_submitted",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

