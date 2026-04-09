#!/bin/bash
set -e

export PORT="${PORT:-8000}"

# Dynamic worker count: 2 * CPU cores + 1, capped at 4 for small containers
CORES=$(nproc 2>/dev/null || echo 1)
WORKERS=$(( CORES * 2 + 1 ))
if [ "$WORKERS" -gt 4 ]; then WORKERS=4; fi
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-$WORKERS}"

echo "==> Running migrations..."
python manage.py migrate --noinput || { echo "Migration failed!"; exit 1; }

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Creating cache table if needed..."
python manage.py createcachetable 2>/dev/null || true

if [ "${RUN_PREFLIGHT:-}" = "1" ]; then
  echo "==> Running production preflight..."
  python manage.py preflight
fi

if [ "${RUN_PREFLIGHT:-0}" = "1" ] || [ "${RUN_PREFLIGHT:-0}" = "true" ]; then
  echo "==> Running production preflight..."
  python manage.py preflight || { echo "Preflight failed — set SKIP_PREFLIGHT=1 only for debugging."; exit 1; }
fi

echo "==> Checking for admin superuser..."
python manage.py shell -c "
import os
from accounts.models import User
pwd = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
if not User.objects.filter(is_superuser=True).exists() and pwd:
    User.objects.create_superuser('admin', 'admin@example.com', password=pwd)
    print('Superuser created.')
else:
    print('Superuser check passed.')
" || true

echo "==> Starting Gunicorn on :$PORT with $WEB_CONCURRENCY workers..."
exec gunicorn schoolms.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers $WEB_CONCURRENCY \
    --threads 2 \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
