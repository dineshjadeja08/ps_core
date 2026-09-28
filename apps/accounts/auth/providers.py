from dataclasses import dataclass

from rest_framework import serializers

from common.firebase import get_firebase_app


@dataclass(frozen=True)
class VerifiedFirebaseToken:
    phone_number: str
    uid: str = ""


class FirebaseTokenError(serializers.ValidationError):
    pass


class FirebaseAdminAuthProvider:
    def verify_id_token(self, id_token: str) -> VerifiedFirebaseToken:
        if not id_token:
            raise FirebaseTokenError("Firebase ID token is required.")

        from firebase_admin import auth as firebase_auth

        app = get_firebase_app()

        try:
            decoded_token = firebase_auth.verify_id_token(id_token, app=app)
        except Exception as exc:
            raise FirebaseTokenError("Invalid Firebase ID token.") from exc

        phone_number = decoded_token.get("phone_number")
        if not phone_number:
            raise FirebaseTokenError("Verified Firebase token is missing a phone number.")

        return VerifiedFirebaseToken(
            phone_number=phone_number,
            uid=decoded_token.get("uid", ""),
        )
