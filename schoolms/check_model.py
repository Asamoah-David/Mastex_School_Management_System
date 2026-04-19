import os, sys, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'schoolms.settings'
sys.path.insert(0, '.')
django.setup()

from academics.models import GradingPolicy, StudentResultSummary
print('get_active_policy:', hasattr(GradingPolicy, 'get_active_policy'))
fields = [f.name for f in StudentResultSummary._meta.get_fields()]
print('StudentResultSummary fields:', fields)
