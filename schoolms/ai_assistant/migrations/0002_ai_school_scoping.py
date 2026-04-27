from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0001_initial'),
        ('schools', '0001_initial'),
    ]

    operations = [
        # AIChatSession: add school FK + total_tokens + index
        migrations.AddField(
            model_name='aichatsession',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='ai_chat_sessions',
                to='schools.school',
                help_text='School context — ensures sessions are tenant-scoped.',
            ),
        ),
        migrations.AddField(
            model_name='aichatsession',
            name='total_tokens',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Cumulative tokens used in this session (input + output).',
            ),
        ),
        migrations.AddIndex(
            model_name='aichatsession',
            index=models.Index(fields=['school', 'user'], name='idx_aichat_school_user'),
        ),
        # PromptTemplate: drop old unique_together on name, add school FK + new constraint
        migrations.AddField(
            model_name='prompttemplate',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='prompt_templates',
                to='schools.school',
                help_text='Leave blank for a global template. Set to override for a specific school.',
            ),
        ),
        migrations.AlterField(
            model_name='prompttemplate',
            name='name',
            field=models.CharField(max_length=255),
        ),
        migrations.AddConstraint(
            model_name='prompttemplate',
            constraint=models.UniqueConstraint(
                fields=['school', 'name'],
                name='uniq_prompttemplate_school_name',
            ),
        ),
    ]
