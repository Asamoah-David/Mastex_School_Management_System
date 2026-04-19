from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0033_uniq_canteenpayment_payment_reference_nonempty"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentdocument",
            name="file",
            field=models.FileField(blank=True, null=True, upload_to="student_documents/%Y/%m/%d/"),
        ),
        migrations.AddField(
            model_name="studentdocument",
            name="notes",
            field=models.TextField(blank=True, default=""),
        ),
    ]
