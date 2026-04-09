#!/usr/bin/env bash
# Railway pre-deploy: runs in a one-off container (see railway.json).
# Must be a real executable path — Railway does not run this through a shell.
set -e
cd /app
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-schoolms.settings}"
python manage.py migrate --noinput
python manage.py createcachetable 2>/dev/null || true
