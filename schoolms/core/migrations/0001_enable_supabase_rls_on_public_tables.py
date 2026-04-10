# Supabase database linter: tables in `public` exposed to PostgREST must have RLS
# enabled. Django connects as the table owner and bypasses RLS by default, so the
# web app is unchanged; anon/authenticated API roles see no rows without policies.
#
# PostgreSQL only (no-op on SQLite).

from django.db import migrations


ENABLE_STATEMENTS = [
    "ALTER TABLE IF EXISTS public.messaging_broadcastnotification ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_broadcastnotification_recipients ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_conversation ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_conversation_participants ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_message ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.notifications_notificationpreference ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.token_blacklist_outstandingtoken ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.token_blacklist_blacklistedtoken ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.django_cache_table ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_aistudentcomment ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_homeworksubmission ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_studentclass ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_onlinemeeting ENABLE ROW LEVEL SECURITY",
]

DISABLE_STATEMENTS = [
    "ALTER TABLE IF EXISTS public.messaging_broadcastnotification DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_broadcastnotification_recipients DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_conversation DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_conversation_participants DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.messaging_message DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.notifications_notificationpreference DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.token_blacklist_outstandingtoken DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.token_blacklist_blacklistedtoken DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.django_cache_table DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_aistudentcomment DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_homeworksubmission DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_studentclass DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.academics_onlinemeeting DISABLE ROW LEVEL SECURITY",
]


def _apply_statements(schema_editor, statements):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def enable_rls(apps, schema_editor):
    _apply_statements(schema_editor, ENABLE_STATEMENTS)


def disable_rls(apps, schema_editor):
    _apply_statements(schema_editor, DISABLE_STATEMENTS)


class Migration(migrations.Migration):

    dependencies = [
        ("messaging", "0001_initial"),
        ("notifications", "0002_notificationpreference_alter_notification_options_and_more"),
        ("academics", "0017_alter_homework_attachment_and_more"),
        ("token_blacklist", "0012_alter_outstandingtoken_user"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
