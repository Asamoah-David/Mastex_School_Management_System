from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0039_canteenpayment_recorded_by_blank"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="buspayment",
            index=models.Index(
                fields=["school", "payment_status", "-payment_date", "-id"],
                name="idx_bus_school_status_date",
            ),
        ),
        migrations.AddIndex(
            model_name="buspayment",
            index=models.Index(
                fields=["student", "payment_status", "-id"],
                name="idx_bus_student_status",
            ),
        ),
        migrations.AddIndex(
            model_name="canteenpayment",
            index=models.Index(
                fields=["student", "payment_status", "-payment_date"],
                name="idx_cant_stu_status",
            ),
        ),
        migrations.AddIndex(
            model_name="canteenpayment",
            index=models.Index(
                fields=["school", "payment_status", "-payment_date"],
                name="idx_cant_school_status",
            ),
        ),
        migrations.AddIndex(
            model_name="hostelfee",
            index=models.Index(
                fields=["school", "student", "-id"],
                name="idx_hostelfee_school_student",
            ),
        ),
        migrations.AddIndex(
            model_name="hostelfee",
            index=models.Index(
                fields=["school", "payment_status", "-id"],
                name="idx_hostelfee_school_status",
            ),
        ),
        migrations.AddIndex(
            model_name="textbooksale",
            index=models.Index(
                fields=["student", "payment_status", "-id"],
                name="idx_tbook_stu_status",
            ),
        ),
        migrations.AddIndex(
            model_name="textbooksale",
            index=models.Index(
                fields=["school", "payment_status", "-id"],
                name="idx_tbook_school_status",
            ),
        ),
    ]
