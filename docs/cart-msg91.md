# Cart and MSG91 OTP rollout

## OTP deployment

The backend offers `SMS` and `WHATSAPP` delivery through MSG91. Both routes use a locally generated six-digit, single-use challenge so expiry and attempt limits are consistent. The database stores only a keyed hash, never the usable OTP.

Configure these server-only variables in Render:

- `OTP_AUTH_PROVIDER=apps.accounts.otp.providers.Msg91OtpProvider`
- `MSG91_AUTH_KEY`: MSG91 authentication key.
- `MSG91_TEMPLATE_ID`: approved MSG91 SMS OTP template ID.
- `MSG91_WHATSAPP_INTEGRATED_NUMBER`: WhatsApp Business number connected to MSG91, including country code.
- `MSG91_WHATSAPP_TEMPLATE_NAME`: approved WhatsApp authentication template name.
- `MSG91_WHATSAPP_TEMPLATE_NAMESPACE`: namespace shown for the approved template in MSG91.
- `MSG91_WHATSAPP_TEMPLATE_LANGUAGE=en`: template language code.
- `MSG91_OTP_EXPIRY_MINUTES=5`: optional challenge lifetime.

The WhatsApp authentication template must expose the OTP as its first body variable and its copy-code URL button variable. WhatsApp authentication templates require Meta eligibility and approval. Keep every credential server-side; never use a `NEXT_PUBLIC_` variable.

The send API accepts `phone_number` plus `channel` (`SMS` or `WHATSAPP`). Resends wait 60 seconds, verification locks after five failed attempts, and successful codes cannot be reused. Tests mock MSG91 and never send a real message. Smoke-test both routes with consumer mobile numbers after the production templates and credentials are configured.

## WhatsApp booking notifications

Set `NOTIFICATION_PROVIDER=apps.notifications.providers.Msg91WhatsAppNotificationProvider` and configure:

- `MSG91_WHATSAPP_NOTIFICATION_TEMPLATE_NAME`: approved fallback utility template.
- `MSG91_WEBHOOK_SECRET`: a long random value required in the `X-MSG91-Webhook-Secret` delivery callback header.
- Optional event-specific template variables: `MSG91_WHATSAPP_TEMPLATE_BOOKING_CONFIRMED`, `MSG91_WHATSAPP_TEMPLATE_PAYMENT_SUCCESSFUL`, `MSG91_WHATSAPP_TEMPLATE_PAYMENT_FAILED`, `MSG91_WHATSAPP_TEMPLATE_TECHNICIAN_ASSIGNED`, `MSG91_WHATSAPP_TEMPLATE_BOOKING_RESCHEDULED`, `MSG91_WHATSAPP_TEMPLATE_BOOKING_CANCELLED`, `MSG91_WHATSAPP_TEMPLATE_REFUND_INITIATED`, and `MSG91_WHATSAPP_TEMPLATE_REFUND_COMPLETED`.

Each notification template must accept four body variables in this order: booking number, service name, scheduled date/time, and notification message. Configure MSG91 delivery reports to call `POST /api/v1/notifications/webhooks/msg91/`; the provider sends the notification UUID as `CRQID` so delivery, read, and failure callbacks reconcile to the correct record.

## Authenticated cart API

- `GET /api/v1/cart/`: account cart, current service prices, total and total advances.
- `POST /api/v1/cart/` with `service_ids`: add available services without duplicates.
- `POST /api/v1/cart/` with `merge: true`: import browser selections.
- `DELETE /api/v1/cart/items/<service_uuid>/`: remove a cart selection.
- `POST /api/v1/cart/checkout/`: reserve selected cart services in one transaction.

Send an `Idempotency-Key` header when checking out. Reuse the same key only to retry the same cart contents and booking details; a reused key with different input is rejected.

## Razorpay payment and refund reliability

- Payment creation locks the booking and enforces a single active advance order.
- Payment creation also accepts `Idempotency-Key`; the same operation returns the existing order.
- Payment and refund webhook payloads are persisted and can be retried safely.
- Admins can initiate full or partial refunds and reconcile pending refund records with Razorpay from the Payments page.

## Validation

Run `.venv/Scripts/python -m pytest` and `manage.py makemigrations --check --dry-run --settings=config.settings.test`. Run frontend typecheck, lint, Vitest, and the production build.
