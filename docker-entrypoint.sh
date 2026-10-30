#!/bin/sh
set -e
# Create tables and load questions/problems (safe to run on every start; it only adds what's missing).
python manage.py init
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python manage.py create-instructor "${ADMIN_NAME:-Admin}" "$ADMIN_EMAIL" "$ADMIN_PASSWORD"
fi
exec gunicorn -c gunicorn.conf.py wsgi:app
