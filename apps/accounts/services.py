from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AdminMfaChallenge, CustomerProfile, User, UserRole
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


def send_login_otp(phone_number: str, channel: str, *, allow_admin=False):
    phone_number = normalize_phone_number(phone_number)
    user = User.objects.filter(phone_number=phone_number).only("role").first()
    if user and user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and not allow_admin:
        raise serializers.ValidationError("Administrator accounts must use password and MFA login.")
    mobile = phone_number.replace("+", "")
    return {
        "phone_number": phone_number,
        "request_id": get_otp_auth_provider().send_otp(mobile=mobile, channel=channel).request_id,
        "channel": channel,
    }


def authenticate_with_otp(phone_number: str, otp: str):
    phone_number = normalize_phone_number(phone_number)
    user = User.objects.filter(phone_number=phone_number).only("role").first()
    if user and user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        raise serializers.ValidationError("Administrator accounts must use password and MFA login.")
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
    if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        raise serializers.ValidationError("Administrator accounts must use password and MFA login.")

    changed_fields = []
    if not user.is_verified:
        user.is_verified = True
        changed_fields.append("is_verified")
    if changed_fields:
        user.save(update_fields=changed_fields + ["updated_at"])

    if user.role == UserRole.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=user)

    return _login_result(user=user, created=created)


@transaction.atomic
def register_with_password(phone_number: str, password: str, **profile_fields):
    phone_number = normalize_phone_number(phone_number)
    existing_user = User.objects.filter(phone_number=phone_number).first()

    if existing_user and existing_user.role != UserRole.CUSTOMER:
        raise serializers.ValidationError("This phone number cannot create a customer account.")

    if existing_user and existing_user.has_usable_password():
        raise serializers.ValidationError("An account already exists for this phone number. Please login.")

    user = existing_user or User(phone_number=phone_number, role=UserRole.CUSTOMER, is_active=True)
    validate_password(password, user=user)

    user.role = user.role or UserRole.CUSTOMER
    user.is_verified = True
    user.is_active = True
    user.set_password(password)

    for field in ("first_name", "last_name", "email"):
        if field in profile_fields:
            value = profile_fields[field]
            setattr(user, field, None if field == "email" and value == "" else value)

    user.save()

    if user.role == UserRole.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=user)

    return _login_result(user=user, created=existing_user is None)


@transaction.atomic
def authenticate_with_password(phone_number: str, password: str, channel="WHATSAPP"):
    phone_number = normalize_phone_number(phone_number)

    try:
        user = User.objects.get(phone_number=phone_number)
    except User.DoesNotExist as exc:
        raise serializers.ValidationError("Invalid phone number or password.") from exc

    if not user.is_active:
        raise serializers.ValidationError("This account is disabled.")

    if not user.has_usable_password() or not user.check_password(password):
        raise serializers.ValidationError("Invalid phone number or password.")

    if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        send_login_otp(user.phone_number, channel, allow_admin=True)
        AdminMfaChallenge.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=timezone.now())
        challenge = AdminMfaChallenge.objects.create(
            user=user,
            channel=channel,
            expires_at=timezone.now() + timezone.timedelta(minutes=settings.ADMIN_MFA_TTL_MINUTES),
        )
        return {
            "mfa_required": True,
            "challenge_id": challenge.id,
            "channel": channel,
            "expires_in": settings.ADMIN_MFA_TTL_MINUTES * 60,
        }

    if user.role == UserRole.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=user)
    return _login_result(user=user, created=False)


@transaction.atomic
def complete_admin_mfa(challenge_id, otp: str):
    challenge = AdminMfaChallenge.objects.select_for_update().select_related("user").filter(id=challenge_id).first()
    now = timezone.now()
    if not challenge or challenge.consumed_at or challenge.expires_at <= now:
        raise serializers.ValidationError("Invalid or expired MFA challenge. Start admin login again.")
    user = challenge.user
    if not user.is_active or user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        raise serializers.ValidationError("This administrator account is not active.")
    mobile = user.phone_number.replace("+", "")
    get_otp_auth_provider().verify_otp(mobile=mobile, otp=otp)
    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at", "updated_at"])
    return _login_result(user=user, created=False, mfa_verified=True)


def _login_result(*, user, created, mfa_verified=False):
    refresh = RefreshToken.for_user(user)
    refresh["mfa"] = bool(mfa_verified)
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
    phone_number = normalize_phone_number(phone_number)
    user = User.objects.filter(phone_number=phone_number).first()
    if user and user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        if not user.is_active:
            raise serializers.ValidationError("This account is disabled.")
        return _login_result(user=user, created=False, mfa_verified=settings.DEBUG)
    return authenticate_verified_phone(phone_number)
