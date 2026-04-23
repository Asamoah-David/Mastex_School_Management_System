from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0046_exam_quiz_new_question_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='ptmeeting',
            name='meeting_link',
            field=models.URLField(blank=True, help_text='Optional video call link (Zoom, Meet, Jitsi, etc.)'),
        ),
    ]
