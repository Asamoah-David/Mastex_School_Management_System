from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0052_exam_quiz_new_question_types"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="gradeboundary",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="gradeboundary",
            name="term",
            field=models.ForeignKey(
                blank=True,
                help_text="Leave blank for the school-wide default scale; set to override for a specific term.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="academics.term",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="gradeboundary",
            unique_together={("school", "term", "grade")},
        ),
    ]
