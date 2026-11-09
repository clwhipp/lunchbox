#!/bin/sh
set -eu
if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --check
fi
exec "$@"
