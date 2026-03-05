#!/bin/bash
set -e

echo "Starting Django Docker container..."

# Apply database migrations
echo "Applying migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Optional: Create admin superuser if not exists
echo "Checking for admin superuser..."
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('admin','admin@example.com','Admin123!') if not User.objects.filter(username='admin').exists() else None"

# Start Gunicorn server using Render's port
echo "Starting Gunicorn..."
exec gunicorn schoolms.wsgi:application --bind 0.0.0.0:$PORT --workers 4