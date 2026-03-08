#!/bin/bash
set -e

echo "Starting Django Docker container..."

# Apply database migrations
echo "Applying migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create admin superuser if none exists (requires DJANGO_SUPERUSER_PASSWORD in env)
echo "Checking for admin superuser..."
python manage.py shell -c "
import os
from accounts.models import User
pwd = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
if not User.objects.filter(is_superuser=True).exists() and pwd:
    User.objects.create_superuser('admin', 'admin@example.com', password=pwd)
    print('Superuser created.')
else:
    print('Superuser already exists.')
"

# Start Gunicorn server using Render's port
echo "Starting Gunicorn..."
exec gunicorn schoolms.wsgi:application --bind 0.0.0.0:$PORT --workers 4