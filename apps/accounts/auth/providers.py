from dataclasses import dataclass
import json
import os

from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers


@dataclass(frozen=True)
class VerifiedFirebaseToken:
    phone_number: str
    uid: str = ""


class FirebaseTokenError(serializers.ValidationError):
    pass


class FirebaseAdminAuthProvider:
    _initialized = False

    @classmethod
    def _ensure_initialized(cls):
        if cls._initialized:
            return

        try:
            import firebase_admin
            from firebase_admin import credentials
        except ImportError as exc:
            raise ImproperlyConfigured(
                "Install and configure firebase-admin to verify Firebase ID tokens."
            ) from exc

        if firebase_admin._apps:
            cls._initialized = True
            return

        credentials_json = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()

        if credentials_json:
            try:
                credential_info = json.loads(credentials_json)
            except json.JSONDecodeError as exc:
                raise ImproperlyConfigured("FIREBASE_CREDENTIALS_JSON is not valid JSON.") from exc
            firebase_admin.initialize_app(credentials.Certificate(credential_info))
        else:
            # Uses GOOGLE_APPLICATION_CREDENTIALS, workload identity, or another ADC source.
            firebase_admin.initialize_app()

        cls._initialized = True

    def verify_id_token(self, id_token: str) -> VerifiedFirebaseToken:
        if not id_token:
            raise FirebaseTokenError("Firebase ID token is required.")

        try:
            from firebase_admin import auth as firebase_auth
        except ImportError as exc:
            raise ImproperlyConfigured(
                "Install and configure firebase-admin to verify Firebase ID tokens."
            ) from exc

        self._ensure_initialized()

        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
        except Exception as exc:
            raise FirebaseTokenError("Invalid Firebase ID token.") from exc

        phone_number = decoded_token.get("phone_number")
        if not phone_number:
            raise FirebaseTokenError("Verified Firebase token is missing a phone number.")

        return VerifiedFirebaseToken(
            phone_number=phone_number,
            uid=decoded_token.get("uid", ""),
        )
