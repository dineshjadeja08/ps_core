# Purple Squad Backend Security

## Secret Handling

Keep `DJANGO_SECRET_KEY`, Razorpay secrets, Firebase credentials, database passwords, and provider API keys outside source control. Configure them through environment variables or the deployment secret store. Do not log full tokens, signatures, passwords, OTPs, or payment payloads.

## Authentication Architecture

Customers can authenticate through the configured phone/OTP or password flow. Administrators must first verify their password and then complete an MSG91 SMS or WhatsApp OTP challenge. Admin JWTs require an `mfa=true` claim, so older tokens and tokens issued outside the MFA flow cannot access any authenticated endpoint. The built-in Django admin route is disabled in production to prevent a password-only bypass.

Access tokens expire after 10 minutes and refresh tokens after seven days. Refresh tokens rotate on every successful refresh and the submitted token is blacklisted, so clients must persist the replacement refresh token. A dedicated `JWT_SIGNING_KEY` is required in production.

Login, OTP send/verify, and payment endpoints have separate per-IP, per-phone, and per-user limits. Production uses Redis so limits are shared across workers. These application limits supplement, rather than replace, Cloudflare/WAF rate limits.

## Payment Security

Payment amounts are calculated on the backend. Razorpay checkout verification uses HMAC signatures, webhooks require `X-Razorpay-Signature`, and webhook bodies are size-limited before processing. Payment and webhook failures return safe API errors.

## Permissions

Customer APIs scope objects to the authenticated customer. Admin operations require an admin or super-admin role. Sensitive admin actions and denied admin access attempts are recorded in `AuditLog`.

## Logging Redaction

Structured logs include request IDs and user IDs, but sensitive values matching token, authorization, signature, and secret fields are redacted. Incident debugging should use `X-Request-ID` rather than raw credential values.

## CORS

Allowed CORS and CSRF origins are environment-based via `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`. Production deployments must set exact frontend origins.

## HTTPS Requirements

Production settings enable SSL redirect, secure cookies, HSTS, content type nosniff, referrer policy, and deny framing. Terminating proxies must forward `X-Forwarded-Proto: https`.

## Swagger Production Policy

Swagger, Redoc, and the OpenAPI schema are controlled by `SHOW_API_DOCS`. Local development enables docs by default; production disables them unless explicitly enabled for a controlled environment.

## Deployment Checks

Run:

```bash
python manage.py check --deploy
```

Before launch, resolve Django deployment warnings and Purple Squad checks for provider secrets, CORS origins, allowed hosts, HTTPS, and cookie settings.

## Incident Response Basics

1. Identify the affected request IDs, users, bookings, payments, and audit log entries.
2. Rotate exposed secrets immediately.
3. Disable affected provider credentials where possible.
4. Preserve logs and database audit rows for investigation.
5. Patch and verify with regression tests before re-enabling affected functionality.
