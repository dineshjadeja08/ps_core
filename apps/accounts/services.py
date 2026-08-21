from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import CustomerProfile, User, UserRole
from apps.accounts.validators import normalize_phone_number


def get_firebase_auth_provider():
    provider_class = import_string(settings.FIREBASE_AUTH_PROVIDER)
    return provider_class()


def get_otp_auth_provider():
    provider_class = import_string(settings.OTP_AUTH_PROVIDER)
    return provider_class()


@transaction.atomic
def authenticate_with_firebase(id_token: str):
    verified_token = get_firebase_auth_provider().verify_id_token(id_token)
    phone_number = normalize_phone_number(verified_token.phone_number)
    return authenticate_verified_phone(phone_number)


def send_login_otp(phone_number: str):
    phone_number = normalize_phone_number(phone_number)
    mobile = phone_number.replace("+", "")
    return {
        "phone_number": phone_number,
        "request_id": get_otp_auth_provider().send_otp(mobile=mobile).request_id,
    }


@transaction.atomic
def authenticate_with_otp(phone_number: str, otp: str):
    phone_number = normalize_phone_number(phone_number)
    mobile = phone_number.replace("+", "")
    get_otp_auth_provider().verify_otp(mobile=mobile, otp=otp)
    return authenticate_verified_phone(phone_number)


@transaction.atomic
def authenticate_verified_phone(phone_number: str):
    phone_number = normalize_phone_number(phone_number)
    user, created = User.objects.get_or_create(
        phone_number=phone_number,
        defaults={
            "role": UserRole.CUSTOMER,
            "is_verified": True,
            "is_active": True,
        },
    )

    if not user.is_active:
        raise serializers.ValidationError("This account is disabled.")

    changed_fields = []
    if not user.is_verified:
        user.is_verified = True
        changed_fields.append("is_verified")
    if changed_fields:
        user.save(update_fields=changed_fields + ["updated_at"])

    if user.role == UserRole.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=user)

    refresh = RefreshToken.for_user(user)
    return {
        "user": user,
        "created": created,
        "tokens": {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "token_type": "Bearer",
        },
    }


@transaction.atomic
def authenticate_dev_phone(phone_number: str):
    return authenticate_verified_phone(phone_number)
