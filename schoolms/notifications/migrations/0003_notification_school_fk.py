from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_notificationpreference_alter_notification_options_and_more'),
        ('schools', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='notifications',
                to='schools.school',
                help_text='School context for tenant-scoped queries and reporting.',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['school', 'created_at'], name='idx_notif_school_created'),
        ),
    ]
