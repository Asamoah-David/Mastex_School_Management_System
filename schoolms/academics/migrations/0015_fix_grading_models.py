"""
Migration 0015: Reconcile GradingPolicy fields and ensure GradePoint,
StudentResultSummary tables exist.

This migration is idempotent — it uses SeparateDatabaseAndState with
RunSQL (IF NOT EXISTS / IF NOT EXISTS column) so it is safe to apply
even when migration 0008 already ran.
"""
from django.db import migrations, models
import django.db.models.deletion


_PG_FIX_GRADINGPOLICY_SQL = """
                DO $$
                BEGIN
                    -- Convert school_id to ForeignKey (allow multiple policies per school)
                    -- by changing the unique constraint if it still exists
                    IF EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE table_name = 'academics_gradingpolicy'
                          AND constraint_name = 'academics_gradingpolicy_school_id_key'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            DROP CONSTRAINT academics_gradingpolicy_school_id_key;
                    END IF;

                    -- name
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='name'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN name varchar(100) NOT NULL DEFAULT 'Default Policy';
                    END IF;

                    -- ca_weight
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='ca_weight'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN ca_weight double precision NOT NULL DEFAULT 50.0;
                    END IF;

                    -- exam_weight
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='exam_weight'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN exam_weight double precision NOT NULL DEFAULT 50.0;
                    END IF;

                    -- is_default
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='is_default'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN is_default boolean NOT NULL DEFAULT false;
                    END IF;

                    -- created_at
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='created_at'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN created_at timestamp with time zone NOT NULL DEFAULT now();
                    END IF;

                    -- legacy fields: ensure they exist with defaults
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='use_custom_grades'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN use_custom_grades boolean NOT NULL DEFAULT false;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='pass_mark'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN pass_mark double precision NOT NULL DEFAULT 50.0;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='allows_decimal'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN allows_decimal boolean NOT NULL DEFAULT true;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='max_score'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN max_score double precision NOT NULL DEFAULT 100.0;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='academics_gradingpolicy' AND column_name='use_weighted_averages'
                    ) THEN
                        ALTER TABLE academics_gradingpolicy
                            ADD COLUMN use_weighted_averages boolean NOT NULL DEFAULT true;
                    END IF;
                END $$;
"""


def _fix_gradingpolicy_fields(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor

    if vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(_PG_FIX_GRADINGPOLICY_SQL)
        return

    if vendor == "sqlite":
        GradingPolicy = apps.get_model("academics", "GradingPolicy")
        table = GradingPolicy._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}

            to_add = [
                ("name", "varchar(100) NOT NULL DEFAULT 'Default Policy'"),
                ("ca_weight", "REAL NOT NULL DEFAULT 50.0"),
                ("exam_weight", "REAL NOT NULL DEFAULT 50.0"),
                ("is_default", "bool NOT NULL DEFAULT 0"),
                ("created_at", "datetime NOT NULL DEFAULT CURRENT_TIMESTAMP"),
                ("use_custom_grades", "bool NOT NULL DEFAULT 0"),
                ("pass_mark", "REAL NOT NULL DEFAULT 50.0"),
                ("allows_decimal", "bool NOT NULL DEFAULT 1"),
                ("max_score", "REAL NOT NULL DEFAULT 100.0"),
                ("use_weighted_averages", "bool NOT NULL DEFAULT 1"),
            ]

            for column, coltype in to_add:
                if column not in existing:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        return


def _create_gradepoint_table(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor

    if vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS academics_gradepoint (
                    id bigserial PRIMARY KEY,
                    school_id integer NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
                    grade varchar(5) NOT NULL,
                    min_score double precision NOT NULL,
                    max_score double precision NOT NULL,
                    point_value double precision NOT NULL,
                    scale varchar(5) NOT NULL DEFAULT '5.0',
                    is_default boolean NOT NULL DEFAULT false,
                    UNIQUE (school_id, grade, scale)
                );
                """
            )
        return

    if vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS academics_gradepoint (
                    id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    school_id integer NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
                    grade varchar(5) NOT NULL,
                    min_score real NOT NULL,
                    max_score real NOT NULL,
                    point_value real NOT NULL,
                    scale varchar(5) NOT NULL DEFAULT '5.0',
                    is_default bool NOT NULL DEFAULT 0,
                    UNIQUE (school_id, grade, scale)
                );
                """
            )
        return


def _create_studentresultsummary_table(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor

    if vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS academics_studentresultsummary (
                    id bigserial PRIMARY KEY,
                    student_id integer NOT NULL REFERENCES students_student(id) ON DELETE CASCADE,
                    subject_id integer NOT NULL REFERENCES academics_subject(id) ON DELETE CASCADE,
                    term_id integer NOT NULL REFERENCES academics_term(id) ON DELETE CASCADE,
                    ca_score double precision NOT NULL DEFAULT 0,
                    exam_score double precision NOT NULL DEFAULT 0,
                    final_score double precision NOT NULL DEFAULT 0,
                    grade varchar(5) NOT NULL DEFAULT '',
                    grade_point double precision NOT NULL DEFAULT 0,
                    term_position integer,
                    cumulative_position integer,
                    gpa double precision NOT NULL DEFAULT 0,
                    cumulative_gpa double precision NOT NULL DEFAULT 0,
                    calculated_at timestamp with time zone NOT NULL DEFAULT now(),
                    UNIQUE (student_id, subject_id, term_id)
                );
                """
            )
        return

    if vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS academics_studentresultsummary (
                    id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    student_id integer NOT NULL REFERENCES students_student(id) ON DELETE CASCADE,
                    subject_id integer NOT NULL REFERENCES academics_subject(id) ON DELETE CASCADE,
                    term_id integer NOT NULL REFERENCES academics_term(id) ON DELETE CASCADE,
                    ca_score real NOT NULL DEFAULT 0,
                    exam_score real NOT NULL DEFAULT 0,
                    final_score real NOT NULL DEFAULT 0,
                    grade varchar(5) NOT NULL DEFAULT '',
                    grade_point real NOT NULL DEFAULT 0,
                    term_position integer,
                    cumulative_position integer,
                    gpa real NOT NULL DEFAULT 0,
                    cumulative_gpa real NOT NULL DEFAULT 0,
                    calculated_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (student_id, subject_id, term_id)
                );
                """
            )
        return


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0012_onlinemeeting_fields'),
        ('students', '0007_add_quiz_and_term_dates'),
        ('schools', '0006_school_subscription_amount'),
    ]

    operations = [
        # ── GradingPolicy: add new columns if missing ────────────────────────
        migrations.RunPython(_fix_gradingpolicy_fields, migrations.RunPython.noop),

        # ── GradePoint table ─────────────────────────────────────────────────
        migrations.RunPython(_create_gradepoint_table, migrations.RunPython.noop),

        # ── StudentResultSummary table ────────────────────────────────────────
        migrations.RunPython(_create_studentresultsummary_table, migrations.RunPython.noop),

        # ── normalized_score: no DB changes needed (it's a property) ─────────

        # Tell Django's migration state about the new fields on GradingPolicy
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='gradingpolicy',
                    name='name',
                    field=models.CharField(default='Default Policy', max_length=100),
                ),
                migrations.AddField(
                    model_name='gradingpolicy',
                    name='ca_weight',
                    field=models.FloatField(default=50.0),
                ),
                migrations.AddField(
                    model_name='gradingpolicy',
                    name='exam_weight',
                    field=models.FloatField(default=50.0),
                ),
                migrations.AddField(
                    model_name='gradingpolicy',
                    name='is_default',
                    field=models.BooleanField(default=False),
                ),
                migrations.AddField(
                    model_name='gradingpolicy',
                    name='created_at',
                    field=models.DateTimeField(auto_now_add=True),
                    preserve_default=False,
                ),
            ],
            database_operations=[],  # already handled by RunSQL above
        ),

        # Tell Django about the new models
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='GradePoint',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                        ('grade', models.CharField(max_length=5)),
                        ('min_score', models.FloatField()),
                        ('max_score', models.FloatField()),
                        ('point_value', models.FloatField()),
                        ('scale', models.CharField(default='5.0', max_length=5)),
                        ('is_default', models.BooleanField(default=False)),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='schools.school')),
                    ],
                    options={'ordering': ['-min_score']},
                ),
                migrations.CreateModel(
                    name='StudentResultSummary',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                        ('ca_score', models.FloatField(default=0)),
                        ('exam_score', models.FloatField(default=0)),
                        ('final_score', models.FloatField(default=0)),
                        ('grade', models.CharField(blank=True, max_length=5)),
                        ('grade_point', models.FloatField(default=0)),
                        ('term_position', models.PositiveIntegerField(blank=True, null=True)),
                        ('cumulative_position', models.PositiveIntegerField(blank=True, null=True)),
                        ('gpa', models.FloatField(default=0)),
                        ('cumulative_gpa', models.FloatField(default=0)),
                        ('calculated_at', models.DateTimeField(auto_now=True)),
                        ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='students.student')),
                        ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.subject')),
                        ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.term')),
                    ],
                ),
            ],
            database_operations=[],  # already handled by RunSQL above
        ),
    ]
