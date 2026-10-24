from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import CustomerProfile, User, UserRole
from apps.accounts.validators import normalize_account_phone_number, normalize_phone_number


def get_firebase_auth_provider():
    provider_class = import_string(settings.FIREBASE_AUTH_PROVIDER)
    return provider_class()


@transaction.atomic
def authenticate_with_firebase(id_token: str, *, app="customer"):
    verified_token = get_firebase_auth_provider().verify_id_token(id_token)
    phone_number = normalize_phone_number(verified_token.phone_number)
    return authenticate_verified_phone(phone_number, firebase_uid=verified_token.uid, app=app)


@transaction.atomic
def authenticate_verified_phone(phone_number: str, *, firebase_uid: str = "", app: str = "customer"):
    """Authenticate a verified phone, requiring an admin-created partner account for PurplePartner."""
    phone_number = normalize_phone_number(phone_number)
    user = User.objects.select_for_update().filter(firebase_uid=firebase_uid).first() if firebase_uid else None
    if user is None:
        user = User.objects.select_for_update().filter(phone_number=phone_number).first()
    created = user is None
    if app == "partner" and user is None:
        raise serializers.ValidationError("This number is not invited to a partner account. Ask your company admin to add you first.")
    if user is None:
        user = User.objects.create(
            phone_number=phone_number,
            firebase_uid=firebase_uid or None,
            role=UserRole.TECHNICIAN if app == "partner" else UserRole.CUSTOMER,
            is_verified=True,
            is_active=True,
        )

    if not user.is_active:
        raise serializers.ValidationError("This account is disabled.")
    if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        raise serializers.ValidationError("Administrator accounts must use the staff login portal.")
    if app == "partner" and user.role != UserRole.TECHNICIAN:
        raise serializers.ValidationError("This number is registered as a Purple Squad customer. Use a different number to join as a partner.")

    if app == "partner":
        from apps.technicians.models import TechnicianCompanyUser, TechnicianProfile

        has_profile = TechnicianProfile.objects.filter(user=user, is_active=True).exists()
        has_active_membership = TechnicianCompanyUser.objects.filter(user=user, is_active=True, technician__is_active=True).exists()
        if not has_profile and not has_active_membership:
            raise serializers.ValidationError("This partner account is not linked to an active company. Ask your company admin to add you.")

    if firebase_uid:
        uid_owner = User.objects.filter(firebase_uid=firebase_uid).exclude(pk=user.pk).first()
        if uid_owner:
            raise serializers.ValidationError("This Firebase identity is already linked to another account.")

    changed_fields = []
    if user.phone_number != phone_number:
        if User.objects.filter(phone_number=phone_number).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This phone number is already linked to another account.")
        user.phone_number = phone_number
        changed_fields.append("phone_number")
    if not user.is_verified:
        user.is_verified = True
        changed_fields.append("is_verified")
    if firebase_uid and user.firebase_uid != firebase_uid:
        user.firebase_uid = firebase_uid
        changed_fields.append("firebase_uid")
    if changed_fields:
        user.save(update_fields=changed_fields + ["updated_at"])

    if user.role == UserRole.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=user)
    return _login_result(user=user, created=created)


@transaction.atomic
def authenticate_with_password(phone_number: str, password: str):
    phone_number = normalize_account_phone_number(phone_number)

    user = User.objects.filter(phone_number=phone_number).first()
    legacy_phone_format = False
    if user is None and phone_number.startswith("+91"):
        # Older local superusers may have been created with a 10-digit phone
        # before the account manager enforced E.164 formatting.
        legacy_numbers = (phone_number[3:], phone_number[1:])
        legacy_users = list(
            User.objects.filter(
                phone_number__in=legacy_numbers,
                role__in=(UserRole.ADMIN, UserRole.SUPER_ADMIN),
            )
        )
        if len(legacy_users) == 1:
            user = legacy_users[0]
            legacy_phone_format = True
    if user is None:
        raise serializers.ValidationError("Invalid phone number or password.")

    if not user.is_active:
        raise serializers.ValidationError("This account is disabled.")

    if not user.has_usable_password() or not user.check_password(password):
        raise serializers.ValidationError("Invalid phone number or password.")

    if legacy_phone_format:
        user.phone_number = phone_number
        user.save(update_fields=["phone_number", "updated_at"])

    if user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        raise serializers.ValidationError("Customers must sign in with Firebase phone verification.")

    if user.role == UserRole.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=user)
    return _login_result(
        user=user,
        created=False,
        mfa_verified=user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN},
    )


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
