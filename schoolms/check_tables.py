import os, sys, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'schoolms.settings'
sys.path.insert(0, '.')
django.setup()

from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = [r[0] for r in cursor.fetchall()]
needed = ['academics_aistudentcomment', 'academics_gradingpolicy', 'academics_studentresultsummary', 'academics_assessmentscore', 'academics_examscore', 'academics_assessmenttype']
for t in needed:
    exists = t in tables
    print(f"{'OK' if exists else 'MISSING'}: {t}")
