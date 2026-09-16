# Cloudflare OTP protection

The application validates Cloudflare Turnstile on every OTP request when
`REQUIRE_TURNSTILE_FOR_OTP=true`. Set `NEXT_PUBLIC_TURNSTILE_SITE_KEY` on the
frontend and `TURNSTILE_SECRET_KEY` on the backend.

Cloudflare edge rate limiting must be configured for the production API zone:

1. Create a rate-limiting rule for `POST /api/v1/auth/otp/send/` at 5 requests
   per 10 minutes per IP. Block for 30 minutes when exceeded.
2. Create a rule for `POST /api/v1/auth/otp/verify/` at 10 requests per 10
   minutes per IP. Block for 30 minutes when exceeded.
3. Create a rule for `/api/v1/bookings/*/payments/order/` and
   `/api/v1/payments/verify/` at 20 requests per minute per IP.
4. Exclude the signed Razorpay webhook path from browser challenges. Its
   signature is verified by the backend and it has a separate API throttle.
5. Keep the backend Redis throttles enabled. Edge rules are an additional
   layer, not a replacement.

After configuring the rules, verify them from a non-allowlisted network and
record screenshots/exported rule definitions in the deployment runbook.
