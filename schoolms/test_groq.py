import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'schoolms.settings'
sys.path.insert(0, '.')

import django
django.setup()

from ai_assistant.utils import ask_ai_with_context
result = ask_ai_with_context("How do I pay school fees?", school_name="Test School", user_name="Test User", user_role="parent")
print("RESULT:", result[:300])
