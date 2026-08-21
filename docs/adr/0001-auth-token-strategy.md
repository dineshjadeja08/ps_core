# ADR 0001: Backend Token Strategy

## Status

Accepted

## Context

Purple Squad customer authentication starts with Firebase Phone Authentication. The frontend receives a Firebase ID token after OTP verification, and the backend must verify that token before trusting the phone number.

The backend still needs its own credentials so the same API can serve web, customer mobile apps, technician apps, and future admin tools without coupling every request to Firebase.

## Decision

Use JWT access and refresh tokens through `djangorestframework-simplejwt`.

The `/api/v1/auth/firebase/` endpoint verifies the Firebase ID token server-side, creates or retrieves the local user, then issues Purple Squad JWT credentials. Access tokens authenticate API requests with `Authorization: Bearer <token>`. Refresh tokens are rotated by `/api/v1/auth/refresh/` and can be blacklisted by `/api/v1/auth/logout/`.

## Consequences

- Frontends get a mobile-friendly stateless access token.
- Refresh-token blacklist support gives logout a server-side effect.
- Firebase remains the phone OTP identity proof, while Django owns local roles, permissions, and profiles.
- Tests can mock the Firebase provider without calling live Firebase.
