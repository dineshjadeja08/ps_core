# Purple Squad backend on Google Cloud

This deployment runs Django on Cloud Run with Cloud SQL, Memorystore, Secret
Manager, and the Firebase Admin SDK through Application Default Credentials.
No Firebase service-account JSON is deployed.

## Target resources

- Project: `purplesquad`
- Service: `purple-squad-api`
- Migration job: `purple-squad-migrate`
- Artifact Registry repository: `purple-squad`
- Runtime service account: `purple-squad-api@purplesquad.iam.gserviceaccount.com`
- Suggested region: `asia-south1` (change every command together if required)

Use a separate staging project before production when possible.

## 1. Bootstrap APIs and service identity

```powershell
gcloud auth login
gcloud config set project purplesquad

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com sqladmin.googleapis.com redis.googleapis.com vpcaccess.googleapis.com identitytoolkit.googleapis.com fcm.googleapis.com

gcloud iam service-accounts create purple-squad-api --display-name="Purple Squad Cloud Run API"

gcloud projects add-iam-policy-binding purplesquad --member="serviceAccount:purple-squad-api@purplesquad.iam.gserviceaccount.com" --role="roles/cloudsql.client"
gcloud projects add-iam-policy-binding purplesquad --member="serviceAccount:purple-squad-api@purplesquad.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud projects add-iam-policy-binding purplesquad --member="serviceAccount:purple-squad-api@purplesquad.iam.gserviceaccount.com" --role="roles/firebasecloudmessaging.admin"

gcloud artifacts repositories create purple-squad --repository-format=docker --location=asia-south1 --description="Purple Squad application images"
```

Granting `roles/firebasecloudmessaging.admin` lets the attached Cloud Run
identity call `firebase_admin.messaging.send()`. Firebase ID-token validation
uses the same project identity and does not need a downloaded key.

## 2. Create data services

Create a Cloud SQL for PostgreSQL instance and database in the same region.
Attach it to Cloud Run with its instance connection name:

```text
purplesquad:asia-south1:purple-squad-db
```

Create a Memorystore for Redis instance on a VPC and configure Cloud Run with
Direct VPC egress. Store the resulting Redis URL as a secret. Never expose
Cloud SQL or Redis directly to the public internet.

The Django `DATABASE_URL` for a Cloud SQL Unix socket has this form (URL-encode
special characters in the password):

```text
postgresql://DB_USER:DB_PASSWORD@/DB_NAME?host=/cloudsql/purplesquad:asia-south1:purple-squad-db
```

## 3. Create Secret Manager values

Create these secrets in Secret Manager. Add values through the console or
stdin; do not put them in source control or shell history.

```text
django-secret-key
jwt-signing-key
database-url
redis-url
google-maps-api-key
razorpay-key-id
razorpay-key-secret
razorpay-webhook-secret
cloudinary-url
msg91-auth-key
```

The Firebase Admin key previously shared during development must be revoked.
Cloud Run ADC replaces it completely.

## 4. Build the image

```powershell
$IMAGE="asia-south1-docker.pkg.dev/purplesquad/purple-squad/api:$(git rev-parse --short HEAD)"
gcloud builds submit --tag $IMAGE .
```

The image builds static files once. The running service never performs schema
migrations or seed operations.

## 5. Deploy the API

Copy `cloud-run.env.yaml.example` to a temporary file outside Git and replace
hostnames if the final domain is not ready. Deploy using the Cloud Run URL
first, then add `api.purplesquad.in` later.

```powershell
gcloud run deploy purple-squad-api `
  --image $IMAGE `
  --region asia-south1 `
  --platform managed `
  --allow-unauthenticated `
  --service-account purple-squad-api@purplesquad.iam.gserviceaccount.com `
  --port 8000 `
  --cpu 1 `
  --memory 1Gi `
  --min 0 `
  --max 10 `
  --concurrency 40 `
  --timeout 120 `
  --add-cloudsql-instances purplesquad:asia-south1:purple-squad-db `
  --env-vars-file deploy/gcp/cloud-run.env.yaml.example `
  --set-secrets "SECRET_KEY=django-secret-key:latest,JWT_SIGNING_KEY=jwt-signing-key:latest,DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,GOOGLE_MAPS_API_KEY=google-maps-api-key:latest,RAZORPAY_KEY_ID=razorpay-key-id:latest,RAZORPAY_KEY_SECRET=razorpay-key-secret:latest,RAZORPAY_WEBHOOK_SECRET=razorpay-webhook-secret:latest,CLOUDINARY_URL=cloudinary-url:latest,MSG91_AUTH_KEY=msg91-auth-key:latest"
```

If using Memorystore, add Direct VPC egress to the service before testing.

## 6. Deploy and execute the migration job

Use the same image, identity, Cloud SQL attachment, non-secret variables, and
secret mappings as the API service. The job command is:

```text
/app/scripts/cloud-run-migrate.sh
```

Create the job in the Cloud Run console or with `gcloud run jobs deploy`, then:

```powershell
gcloud run jobs execute purple-squad-migrate --region asia-south1 --wait
```

Run the job once for each release that includes migrations, before directing
production traffic to the new revision. Catalogue seeding is intentionally not
automatic because it can overwrite operator-managed content.

## 7. Verify

1. `GET /api/v1/health/` returns `200`.
2. Firebase phone login exchanges an ID token at `/api/v1/auth/firebase-login/`.
3. Firebase Phone Authentication sends and verifies the login OTP.
4. A booking event creates a `SENT` SMS notification with provider `msg91-sms`.
5. Google Places/geocoding, Razorpay webhooks, and Cloudinary uploads succeed.
6. Cloud Logging contains no `failure.category` events during the acceptance flow.

## MSG91 transactional SMS

Firebase Phone Authentication remains responsible only for login OTP. Booking,
payment, technician, refund, review, and admin reminder messages use MSG91's SMS
Flow API.

The initial rollout intentionally enables only `BOOKING_CONFIRMED`,
`TECHNICIAN_ASSIGNED`, and `REVIEW_REQUEST` through
`MSG91_SMS_ENABLED_EVENTS`. Other business workflows continue normally but do
not send SMS or consume MSG91 credits. Add another
event only after its DLT/MSG91 template is approved.

Create approved MSG91/DLT templates with two variables. The provider supplies
event-aware values:

```text
VAR1 = booking/lead reference, amount for payment-link messages
VAR2 = schedule, technician name, service, amount, title, or shortened payment URL
```

For example, a payment-pending template can contain the amount as its first
variable and the payment URL as its second variable. A booking-confirmed
template can contain the booking number and schedule. MSG91's `short_url`
option is enabled for payment links.

Set `MSG91_SMS_TEMPLATE_ID` to a generic fallback template ID. For event-specific
DLT templates, set `MSG91_SMS_TEMPLATE_<EVENT>` (for example,
`MSG91_SMS_TEMPLATE_PAYMENT_PENDING`). Event-specific IDs override the fallback.
Store `MSG91_AUTH_KEY` only in Secret Manager.

Use a global external Application Load Balancer for the production
`api.purplesquad.in` domain. Direct Cloud Run domain mapping is preview and is
not the recommended production option.
