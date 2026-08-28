# Purple Squad Deployment

Phase 13 target:

- Django backend on Render
- Neon PostgreSQL database using the pooled connection URL
- Render free Web Service for development/staging
- Frontend later on Vercel
- Cloudflare DNS/domain in front of the frontend/backend hostnames

## Render Resources

Use `render.yaml` as the first deployment blueprint. It defines:

- Docker web service: `purple-squad-backend`
- Free Render plan for development
- Neon database connection through `DATABASE_URL`
- Health check path: `/api/v1/health/`
- Docker start command:

```bash
sh -c 'python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile -'
```

Render free services do not provide durable filesystem storage for uploaded media. Uploaded service images may disappear after rebuilds/restarts. Before accepting real customer bookings, move media storage to S3, Cloudflare R2, or another durable object store.

## Required Environment Variables

Do not commit real values.

```text
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<long random secret>
DEBUG=False
ALLOWED_HOSTS=ps-core.onrender.com
DATABASE_URL=<Neon pooled PostgreSQL URL with sslmode=require>
CORS_ALLOWED_ORIGINS=https://FRONTEND_DOMAIN.vercel.app
CSRF_TRUSTED_ORIGINS=https://ps-core.onrender.com,https://FRONTEND_DOMAIN.vercel.app

OTP_AUTH_PROVIDER=apps.accounts.otp.providers.Msg91OtpProvider
MSG91_AUTH_KEY=<MSG91 auth key, backend secret only>
MSG91_TEMPLATE_ID=<approved MSG91 OTP template id>
MSG91_OTP_EXPIRY_MINUTES=5

RAZORPAY_KEY_ID=<test or live key id>
RAZORPAY_KEY_SECRET=<test or live secret>
RAZORPAY_WEBHOOK_SECRET=<Razorpay webhook signing secret>
RAZORPAY_ADAPTER=apps.payments.providers.RazorpayApiAdapter

NOTIFICATION_PROVIDER=apps.notifications.providers.LocalNotificationProvider
DEV_PHONE_LOGIN_ENABLED=false
SHOW_API_DOCS=false
LOG_LEVEL=INFO
```

Copy Neon's pooled connection string into Render's `DATABASE_URL` environment variable. It should look like:

```text
postgresql://USER:PASSWORD@HOST-pooler.REGION.aws.neon.tech/DATABASE?sslmode=require
```

Do not commit that URL. Replace `FRONTEND_DOMAIN` after Vercel gives you the actual frontend domain. Do not include trailing slashes in `CORS_ALLOWED_ORIGINS` or `CSRF_TRUSTED_ORIGINS`.

Start with MSG91/Razorpay sandbox or test credentials where available. Switch to live credentials only after acceptance testing passes. Never use the Firebase Admin keys that were pasted during development; revoke them in Google Cloud first.

## Static and Media Strategy

Static files are served by WhiteNoise from `STATIC_ROOT` after `collectstatic`.

Uploaded media currently uses Django filesystem storage at `MEDIA_ROOT=/app/media`. On Render free services, this is ephemeral. For production, move media to S3, Cloudflare R2, or another object store and update `STORAGES["default"]`.

## Staging Checklist

1. Create Render staging blueprint from `render.yaml`.
2. Create a Neon PostgreSQL database and copy the pooled connection URL.
3. Paste the Neon pooled URL into Render `DATABASE_URL`.
4. Set staging domain in `ALLOWED_HOSTS`.
5. Set Vercel preview/staging frontend origin in `CORS_ALLOWED_ORIGINS`.
6. Set backend/frontend HTTPS origins in `CSRF_TRUSTED_ORIGINS`.
7. Revoke every Firebase Admin key that was pasted during development.
8. Add MSG91 auth key and approved OTP template ID only as backend secrets.
9. Confirm MSG91 DLT/sender/template setup is approved for India.
10. Add Razorpay test keys and webhook secret.
11. Deploy.
12. Confirm `/api/v1/health/` returns `200`.
13. Run `python manage.py seed_service_areas` for Chennai, Bangalore, and Coimbatore launch coverage.
14. Run `python manage.py seed_catalogue` for the Purple Squad service catalogue.
15. Create a staging superuser.
16. Run the backend acceptance flow with test payments.
17. Confirm duplicate webhook handling and audit logs.

## Production Checklist

1. Create production Render service and Neon PostgreSQL database.
2. Set Cloudflare DNS for the API hostname.
3. Configure HTTPS and final allowed hosts/origins.
4. Rotate from staging secrets to production secrets.
5. Set Razorpay live keys only after test mode has passed.
6. Confirm `SHOW_API_DOCS=false`.
7. Confirm the Render start command runs migrations, collectstatic, and Gunicorn successfully.
8. Run `python manage.py seed_service_areas` and `python manage.py seed_catalogue`.
9. Create production superuser.
10. Verify admin login at `/admin/`.
11. Verify health endpoint.
12. Run acceptance flow with a controlled live payment.
13. Enable monitoring and backup alerts.

## Superuser Creation

Interactive option from the Render shell after migrations:

```bash
python manage.py createsuperuser
```

Non-interactive option from the Render shell or one-off job:

```bash
DJANGO_SUPERUSER_PHONE_NUMBER=+91XXXXXXXXXX \
DJANGO_SUPERUSER_EMAIL=admin@example.com \
DJANGO_SUPERUSER_PASSWORD='use-a-long-random-password' \
python manage.py ensure_superuser
```

Use a secure admin phone number and password. Store credentials in the team password manager. Remove `DJANGO_SUPERUSER_PASSWORD` from the service environment after the admin user has been created if it was added temporarily.

## One-Off Render Commands

Run these from the Render Shell after the service is deployed:

```bash
python manage.py migrate --noinput
python manage.py seed_service_areas
python manage.py seed_catalogue
```

Then create or update the superuser:

```bash
DJANGO_SUPERUSER_PHONE_NUMBER=+91XXXXXXXXXX DJANGO_SUPERUSER_EMAIL=admin@example.com DJANGO_SUPERUSER_PASSWORD='use-a-long-random-password' python manage.py ensure_superuser
```

Do not put `DJANGO_SUPERUSER_PASSWORD` permanently in Render environment variables.

## Admin Catalogue Verification

After creating the superuser:

1. Open `/admin/`.
2. Log in with the superuser phone number and password.
3. Confirm access to Users and Customer profiles.
4. Confirm service categories can be created/edited.
5. Confirm services can be created/edited with prices, descriptions, advance settings, and cover images.
6. Confirm service gallery images can be uploaded and viewed from the customer frontend.

## Real Integration Acceptance Flow

Run this once in staging with test/sandbox credentials and once in production with a controlled live payment:

1. Customer opens frontend and requests phone OTP.
2. Frontend calls `POST /api/v1/auth/otp/send/`.
3. Customer enters OTP.
4. Frontend calls `POST /api/v1/auth/otp/verify/` and receives Purple Squad JWT credentials.
5. Customer adds or selects a serviceable address.
6. Customer selects service and slot.
7. Customer creates booking.
8. Customer opens Razorpay Checkout and pays advance.
9. Backend verifies payment signature through `POST /api/v1/payments/verify/`.
10. Confirm duplicate payment webhook is idempotent.
11. Admin assigns technician from Django admin or admin API.
12. Technician starts and completes booking.
13. Admin records/validates balance collection if required.
14. Customer submits review after completion.

## API Freeze

Before frontend handoff or production launch:

```bash
python manage.py spectacular --settings=config.settings.test --file docs/openapi.yaml --validate
copy docs\openapi.yaml customer-frontend\docs\openapi.yaml
```

Review and freeze:

- Endpoint names and paths
- Request/response schemas
- Error envelope format
- Pagination shape
- Auth headers
- Booking statuses
- Payment statuses
- Image URL fields
- Admin permissions
- Field naming

After this point, change API contracts only for bugs or explicit versioned changes.

## Backup Strategy

Use Render PostgreSQL automated backups for daily point-in-time recovery where available for the selected plan. Before major releases:

```bash
pg_dump "$DATABASE_URL" > purple_squad_backup_$(date +%Y%m%d_%H%M%S).sql
```

Store manual backups in encrypted storage with access limited to operators. Test restore procedures before production launch.

## Deployment Checks

Run locally with production-style environment variables:

```bash
python manage.py check --deploy
python manage.py spectacular --validate
pytest
```

Warnings or errors from `check --deploy` must be resolved before live traffic.
