# Generated migration to add missing Result fields and fix Timetable
# Idempotent: PostgreSQL uses DO blocks; SQLite uses PRAGMA + ALTER TABLE.

from django.db import migrations, models


_PG_RESULT_COLUMN_SQL = [
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='academics_result' AND column_name='created_by_id') THEN
            ALTER TABLE academics_result ADD COLUMN created_by_id integer REFERENCES accounts_user(id) ON DELETE SET NULL;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='academics_result' AND column_name='created_at') THEN
            ALTER TABLE academics_result ADD COLUMN created_at timestamp with time zone DEFAULT NOW();
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='academics_result' AND column_name='remarks') THEN
            ALTER TABLE academics_result ADD COLUMN remarks text DEFAULT '';
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='academics_result' AND column_name='subject_id') THEN
            ALTER TABLE academics_result ADD COLUMN subject_id integer REFERENCES academics_subject(id) ON DELETE CASCADE;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='academics_result' AND column_name='student_id') THEN
            ALTER TABLE academics_result ADD COLUMN student_id integer REFERENCES students_student(id) ON DELETE CASCADE;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='academics_result' AND column_name='total_score') THEN
            ALTER TABLE academics_result ADD COLUMN total_score double precision DEFAULT 100;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='academics_result' AND column_name='updated_at') THEN
            ALTER TABLE academics_result ADD COLUMN updated_at timestamp with time zone DEFAULT NOW();
        END IF;
    END $$;
    """,
]


def _add_result_columns(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor

    if vendor == "postgresql":
        with connection.cursor() as cursor:
            for block in _PG_RESULT_COLUMN_SQL:
                cursor.execute(block)
        return

    if vendor == "sqlite":
        Result = apps.get_model("academics", "Result")
        table = Result._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}
            # Mirrors PostgreSQL branch: only add columns that are missing.
            to_add = [
                ("created_by_id", "INTEGER NULL"),
                ("created_at", "datetime NULL"),
                ("remarks", "TEXT NOT NULL DEFAULT ''"),
                ("subject_id", "INTEGER NULL"),
                ("student_id", "INTEGER NULL"),
                ("total_score", "REAL NOT NULL DEFAULT 100"),
                ("updated_at", "datetime NULL"),
            ]
            for column, coltype in to_add:
                if column not in existing:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        return


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0009_alter_gradingpolicy_unique_together"),
    ]

    operations = [
        migrations.RenameField(
            model_name="timetable",
            old_name="day",
            new_name="day_of_week",
        ),
        migrations.RunPython(_add_result_columns, migrations.RunPython.noop),
    ]
