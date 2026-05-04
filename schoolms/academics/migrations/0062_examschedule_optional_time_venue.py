from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0061_erp_new_models_batch'),
    ]

    operations = [
        migrations.AlterField(
            model_name='examschedule',
            name='start_time',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='examschedule',
            name='end_time',
            field=models.TimeField(null=True, blank=True),
        ),
    ]
