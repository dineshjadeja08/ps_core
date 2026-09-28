#!/bin/sh
set -eu

# Schema changes run in the dedicated Cloud Run migration job. Keeping the
# service entrypoint side-effect free prevents concurrent instances racing.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
