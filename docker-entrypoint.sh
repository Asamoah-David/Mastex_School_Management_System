#!/bin/bash
set -e

# Render sets PORT; default for local Docker
export PORT="${PORT:-8000}"

echo "Starting Django Docker container..."

# Apply database migrations (required for Render; runs on every container start)
echo "Applying migrations..."
python manage.py migrate --noinput || { echo "Migration failed."; exit 1; }

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create admin superuser if none exists (optional; do not fail deploy if this fails)
echo "Checking for admin superuser..."
python manage.py shell -c "
import os
from accounts.models import User
pwd = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
if not User.objects.filter(is_superuser=True).exists() and pwd:
    User.objects.create_superuser('admin', 'admin@example.com', password=pwd)
    print('Superuser created.')
else:
    print('Superuser already exists or no password set.')
" || true

# Start Gunicorn (Render expects app to listen on 0.0.0.0:PORT)
echo "Starting Gunicorn on port $PORT..."
exec gunicorn schoolms.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 2