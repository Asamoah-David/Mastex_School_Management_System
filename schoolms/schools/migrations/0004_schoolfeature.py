from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0003_school_logo_url_academic_year"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolFeature",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(choices=[("hostel", "Hostel"), ("library", "Library"), ("inventory", "Inventory"), ("messaging", "Messaging"), ("ai_assistant", "AI Assistant"), ("finance_admin", "Finance (admin tools)")], max_length=40)),
                ("enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="features", to="schools.school")),
            ],
            options={
                "ordering": ["key"],
                "unique_together": {("school", "key")},
            },
        ),
    ]

