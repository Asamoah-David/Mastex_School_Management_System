import os, sys, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'schoolms.settings'
sys.path.insert(0, '.')
django.setup()

from django.db import connection

# Create the missing academics_studentresultsummary table
sql = """
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
);
"""

with connection.cursor() as cursor:
    cursor.execute(sql)
    print("Table created (or already exists).")

# Verify
cursor = connection.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='academics_studentresultsummary';")
result = cursor.fetchone()
print("Table exists:", result is not None)
