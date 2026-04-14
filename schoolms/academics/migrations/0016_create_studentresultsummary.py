"""
Migration to ensure the academics_studentresultsummary table exists.
Uses RunPython so it works on both SQLite (local dev) and PostgreSQL (Railway production).
"""
from django.db import migrations


def create_table_if_missing(apps, schema_editor):
    """Create the academics_studentresultsummary table if it doesn't already exist.
    Uses database-vendor-aware SQL so it works on both SQLite and PostgreSQL."""
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        # Check if table already exists
        if vendor == 'postgresql':
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'academics_studentresultsummary'
                )
            """)
            exists = cursor.fetchone()[0]
        else:
            # SQLite
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='academics_studentresultsummary'"
            )
            exists = bool(cursor.fetchone())

        if exists:
            return  # Table already created by 0015_fix_grading_models or 0011

        if vendor == 'postgresql':
            cursor.execute("""
                CREATE TABLE "academics_studentresultsummary" (
                    "id" bigserial NOT NULL PRIMARY KEY,
                    "ca_score" numeric(5, 2) NULL,
                    "exam_score" numeric(5, 2) NULL,
                    "final_score" numeric(5, 2) NULL,
                    "grade" varchar(5) NOT NULL DEFAULT '',
                    "grade_point" numeric(4, 2) NULL,
                    "term_position" integer NULL,
                    "cumulative_position" integer NULL,
                    "gpa" numeric(4, 2) NULL,
                    "cumulative_gpa" numeric(4, 2) NULL,
                    "calculated_at" timestamp with time zone NOT NULL DEFAULT now(),
                    "student_id" integer NOT NULL
                        REFERENCES "students_student" ("id") DEFERRABLE INITIALLY DEFERRED,
                    "subject_id" integer NOT NULL
                        REFERENCES "academics_subject" ("id") DEFERRABLE INITIALLY DEFERRED,
                    "term_id" integer NULL
                        REFERENCES "academics_term" ("id") DEFERRABLE INITIALLY DEFERRED
                )
            """)
        else:
            # SQLite
            cursor.execute("""
                CREATE TABLE "academics_studentresultsummary" (
                    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    "ca_score" decimal(5, 2) NULL,
                    "exam_score" decimal(5, 2) NULL,
                    "final_score" decimal(5, 2) NULL,
                    "grade" varchar(5) NOT NULL DEFAULT '',
                    "grade_point" decimal(4, 2) NULL,
                    "term_position" integer NULL,
                    "cumulative_position" integer NULL,
                    "gpa" decimal(4, 2) NULL,
                    "cumulative_gpa" decimal(4, 2) NULL,
                    "calculated_at" datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    "student_id" integer NOT NULL REFERENCES "students_student" ("id"),
                    "subject_id" integer NOT NULL REFERENCES "academics_subject" ("id"),
                    "term_id" integer NULL REFERENCES "academics_term" ("id")
                )
            """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0015_fix_grading_models"),
    ]

    operations = [
        migrations.RunPython(create_table_if_missing, reverse_code=noop),
    ]
