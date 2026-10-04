#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py setup_staff_groups
python manage.py seed_service_areas --keep-existing-active
python manage.py sync_seo_area_pages
