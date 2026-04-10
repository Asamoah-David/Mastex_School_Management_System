# Supabase linter 0013: RLS on public tables exposed to PostgREST.
# Django uses the table owner and bypasses RLS; anon/API roles see nothing without policies.

from django.db import migrations


ENABLE = [
    "ALTER TABLE IF EXISTS public.messaging_outboundcommlog ENABLE ROW LEVEL SECURITY",
]

DISABLE = [
    "ALTER TABLE IF EXISTS public.messaging_outboundcommlog DISABLE ROW LEVEL SECURITY",
]


def _run(schema_editor, statements):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def enable_rls(apps, schema_editor):
    _run(schema_editor, ENABLE)


def disable_rls(apps, schema_editor):
    _run(schema_editor, DISABLE)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_enable_supabase_rls_on_public_tables"),
        ("messaging", "0002_outbound_comm_log"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
