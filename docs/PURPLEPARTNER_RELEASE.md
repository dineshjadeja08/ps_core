# PurplePartner release: partner app backend

Adds what the PurplePartner app (technician app), the customer app's service OTP and the admin KYC review need.

## What changes

- **Partner sign-up:** `POST /api/v1/auth/firebase/` accepts `app: "partner"`. Unknown numbers become pending `TECHNICIAN` users with a `PSP-xxxxxx` profile; numbers already registered as customers are refused.
- **KYC:**
  - Partners: `PATCH /technician/profile/`, `GET /technician/skills/`, `/technician/documents/` (Aadhaar front/back, PAN, photo, certificates) and `POST /technician/kyc/submit/`.
  - Admins: list with `GET /admin/technicians/?verification=UNDER_REVIEW`, review and approve or reject at `/admin/technicians/{id}/kyc/`.
- **Service-start OTP:** every booking gets a 4-digit `start_otp`, and existing bookings are backfilled by the migration.
  - Customers read it at `GET /bookings/{id}/start-otp/`.
  - Technicians must send it to `POST /technician/jobs/{id}/start/` once the job is `TECHNICIAN_ARRIVED`. It locks after 5 wrong tries.
  - Admin start/complete operations do not need the OTP.
- **Job steps:**
  - `POST /technician/jobs/{id}/accept/` records `accepted_at`. Start travelling also records it if the technician skipped Accept.
  - Arriving now also records `arrived_at`.
  - Reassigning a job clears both.
  - Bookings expose `accepted_at`, `arrived_at`, `start_otp_verified` and a customer-safe `technician` summary.
- **Completion proof:** `/technician/jobs/{id}/photos/` (BEFORE, AFTER, RECEIPT); admins read it at `/admin/bookings/{id}/photos/`.
- **Cash and UPI:** `POST /technician/jobs/{id}/collect-balance/` lets the technician record the balance they collected, which completion requires.
- **Partner self-service:** `/technician/earnings/`, `/technician/performance/`, `/technician/reviews/`, `/technician/leaves/`.
- **Job alerts:** when a job is assigned, technicians who registered a device via `POST /api/v1/devices/register/` get a `JOB_ASSIGNED` push. `DELETE` on the same path removes the token on logout. PUSH notifications now use their own provider instead of the SMS provider.

## Deploy

1. Deploy the backend image without traffic, then run `/app/scripts/cloud-run-migrate.sh` with that image. New migrations:
   - `audit/0012_technician_partner_actions`
   - `bookings/0008_booking_start_otp_and_job_steps` (includes the OTP backfill)
   - `notifications/0009_job_assigned_event`
   - `technicians/0005_job_photos_and_partner_kyc`
   - `bookings/0009_rollback_safe_defaults` and `technicians/0006_rollback_safe_defaults`, which add database defaults so the previous revision can still create bookings and technicians while traffic moves, and after a rollback
2. Optional environment variable: `PUSH_NOTIFICATION_PROVIDER`. It defaults to `apps.notifications.fcm.FirebaseCloudMessagingProvider`, using the existing Firebase Admin credentials.
3. KYC documents and job photos use the default media storage (Cloudinary in production).
4. Release the customer app and website that show the service OTP **together with** this backend, otherwise technicians cannot start jobs. Until then, admins can start jobs from the admin panel.
5. The migration job now also runs `sync_technician_skills`, which creates one technician skill per active service category, so new partners have services to pick during KYC. It never edits or removes skills.
