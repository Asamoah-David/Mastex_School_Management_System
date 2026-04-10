# Generated manually for quiz/report reliability

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0017_alter_homework_attachment_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quizanswer",
            name="answer",
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name="quizquestion",
            name="correct_answer",
            field=models.CharField(max_length=200),
        ),
    ]
