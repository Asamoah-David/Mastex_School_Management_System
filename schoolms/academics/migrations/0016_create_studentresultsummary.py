"""
Migration to ensure the academics_studentresultsummary table exists.
This was faked in a previous deployment but the table was never physically created.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0015_fix_grading_models"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS "academics_studentresultsummary" (
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
                "calculated_at" datetime NOT NULL,
                "student_id" integer NOT NULL REFERENCES "students_student" ("id"),
                "subject_id" integer NOT NULL REFERENCES "academics_subject" ("id"),
                "term_id" integer NULL REFERENCES "academics_term" ("id")
            )
            """,
            reverse_sql="DROP TABLE IF EXISTS academics_studentresultsummary",
        ),
    ]
