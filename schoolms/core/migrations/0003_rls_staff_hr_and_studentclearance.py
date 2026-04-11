# Supabase linter 0013: RLS on public tables exposed to PostgREST.

from django.db import migrations


ENABLE = [
    "ALTER TABLE IF EXISTS public.accounts_staffpayrollpayment ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.accounts_staffcontract ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.accounts_staffrolechangelog ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.accounts_staffteachingassignment ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.students_studentclearance ENABLE ROW LEVEL SECURITY",
]

DISABLE = [
    "ALTER TABLE IF EXISTS public.accounts_staffpayrollpayment DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.accounts_staffcontract DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.accounts_staffrolechangelog DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.accounts_staffteachingassignment DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE IF EXISTS public.students_studentclearance DISABLE ROW LEVEL SECURITY",
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
        ("core", "0002_rls_messaging_outboundcommlog"),
        ("accounts", "0015_staff_payroll_payout_and_paystack"),
        ("students", "0014_studentclearance"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
