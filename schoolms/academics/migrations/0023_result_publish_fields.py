from django.db import migrations, models
import django.utils.timezone


def mark_existing_results_published(apps, schema_editor):
    Result = apps.get_model("academics", "Result")
    now = django.utils.timezone.now()
    Result.objects.filter(is_published=False).update(
        is_published=True,
        published_at=now,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0022_merge_20260414_0605"),
    ]

    operations = [
        migrations.AddField(
            model_name="result",
            name="is_published",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Only published results are visible to students/parents.",
            ),
        ),
        migrations.AddField(
            model_name="result",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="published_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="results_published",
                to="accounts.user",
            ),
        ),
        migrations.RunPython(mark_existing_results_published, noop),
    ]
