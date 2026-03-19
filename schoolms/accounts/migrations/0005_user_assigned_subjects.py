# Generated manually for User assigned_subjects

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_user_role'),
        ('academics', '0006_add_quiz_and_term_dates'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='assigned_subjects',
            field=models.ManyToManyField(blank=True, related_name='assigned_teachers', to='academics.subject'),
        ),
    ]
