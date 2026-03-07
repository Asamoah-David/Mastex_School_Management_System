// filepath: c:\Users\Bernard\Desktop\Mastex_School_Management_System\docker-entrypoint.sh
#!/bin/bash
set -e

echo "Starting Django Docker container..."

# Apply database migrations
echo "Applying migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Optional: Create admin superuser if not exists (with error handling)
echo "Checking for admin superuser..."
if ! python manage.py shell -c "from django.contrib.auth.models import User; print('Superuser exists')" 2>/dev/null; then
    python manage.py createsuperuser --noinput --username admin --email admin@example.com || echo "Superuser creation skipped or failed"
fi

# Start Gunicorn server using Render's port
echo "Starting Gunicorn..."
exec gunicorn schoolms.wsgi:application --bind 0.0.0.0:$PORT --workers 4