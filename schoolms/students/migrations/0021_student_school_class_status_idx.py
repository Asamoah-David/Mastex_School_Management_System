# Generated manually for school dashboard / class roster query patterns.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0020_erp_new_models_batch"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="student",
            index=models.Index(
                fields=["school", "school_class", "status"],
                name="idx_stud_sch_cls_stat",
            ),
        ),
    ]
