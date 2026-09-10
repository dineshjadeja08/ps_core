# Cart and Fast2SMS rollout

## Deployment order

Deploy the backend first. The startup script runs migrations, adding `bookings.CartItem` and `accounts.LoginOtpChallenge`. Existing booking and payment endpoints remain compatible with the currently deployed frontend. Publish the updated frontend only after its review is approved.

In Render, configure these server-only environment variables:

- `OTP_AUTH_PROVIDER=apps.accounts.otp.providers.Fast2SmsOtpProvider`
- `FAST2SMS_API_KEY`: the Fast2SMS API authorization key, entered in Render, never in source or a NEXT_PUBLIC variable.
- `FAST2SMS_OTP_TTL_SECONDS=300` (optional; five minutes by default).

The Render blueprint now selects Fast2SMS. Existing manually configured services must update their provider variable too. `REQUIRE_OTP_PROVIDER_CONFIG=true` can enforce key presence at startup once configured. Without a key, OTP requests fail with a generic configuration error; they never log a usable OTP or issue a login token. Password login is unchanged.

Fast2SMS uses the OTP SMS route, POST https://www.fast2sms.com/dev/bulkV2 with authorization in the header. Reference: https://www.fast2sms.com/otp-sms/. This backend supports Indian mobile numbers and six-digit codes. The DB stores a keyed hash, expiry, resend timestamp, attempt count, and consumption timestamp. Resends wait 60 seconds; verification locks after five failed attempts. Codes are single-use. Delivery and live verification must be smoke-tested with an approved test number after credentials are configured. Tests mock the provider and never send SMS.

## Authenticated cart API

- GET `/api/v1/cart/`: account cart, current service prices, total and total advances. Paid services are removed from the cart, not from booking history.
- POST `/api/v1/cart/` with `service_ids: [uuid, ...]`: add available services without duplicates. Prices supplied by clients are ignored.
- POST the same endpoint with `merge: true`: import browser selections, reporting unavailable IDs. Optional `booking_ids: {service_uuid: booking_uuid}` preserves existing pending checkouts after validating customer and service ownership.
- DELETE `/api/v1/cart/items/<service_uuid>/`: remove a cart selection; does not cancel its booking.
- POST `/api/v1/cart/checkout/` with `items: [{service_id, address_id, slot_id, problem_description, customer_notes?}, ...]`: reserve selected cart services in one transaction. Failure rolls back the entire submitted batch. Retrying a pending checkout returns its original booking. Each address must belong to the authenticated customer and each slot must remain available and serve that address.

All cart writes serialize on the account row; slots are locked in a consistent order for multi-item checkout. Service IDs are unique within a cart. Maximum 100 services. Carts and pending checkout references sync between signed-in devices. Guests use browser storage until sign-in. The frontend uses the cart checkout API for scheduling each service and the existing per-booking payment flow. This rollout does not combine Razorpay payments for different bookings into one charge.

## Validation

Run `.venv/Scripts/python -m pytest` and `manage.py makemigrations --check --dry-run --settings=config.settings.test`. Run frontend typecheck, lint, Vitest and production build. Phone QA covers homepage swipe rows, uncropped photos, cart count/add/remove, guest-to-account merge, sign-in handoff, address/date/slot controls, and server checkout retries.
