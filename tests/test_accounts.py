from dataclasses import dataclass

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.auth.providers import FirebaseTokenError
from apps.accounts.models import CustomerProfile, User, UserRole


@dataclass(frozen=True)
class TokenResult:
    phone_number: str
    uid: str = "firebase-uid"


class FakeProvider:
    phone_number = "+919876543210"
    error = None

    def verify_id_token(self, id_token):
        if self.error:
            raise self.error
        return TokenResult(phone_number=self.phone_number)


class FakeOtpProvider:
    sent_mobile = ""
    verified_mobile = ""
    verified_otp = ""
    fail_send = False
    fail_verify = False

    def send_otp(self, *, mobile):
        if self.fail_send:
            from rest_framework import serializers

            raise serializers.ValidationError("Could not send OTP.")
        self.__class__.sent_mobile = mobile
        return type("Result", (), {"request_id": "otp-request-id"})()

    def verify_otp(self, *, mobile, otp):
        if self.fail_verify:
            from rest_framework import serializers

            raise serializers.ValidationError("Invalid or expired OTP.")
        self.__class__.verified_mobile = mobile
        self.__class__.verified_otp = otp
        return type("Result", (), {"request_id": "otp-request-id"})()


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch):
    cache.clear()
    monkeypatch.setattr("apps.accounts.services.get_firebase_auth_provider", FakeProvider)
    monkeypatch.setattr("apps.accounts.services.get_otp_auth_provider", FakeOtpProvider)
    FakeProvider.phone_number = "+919876543210"
    FakeProvider.error = None
    FakeOtpProvider.sent_mobile = ""
    FakeOtpProvider.verified_mobile = ""
    FakeOtpProvider.verified_otp = ""
    FakeOtpProvider.fail_send = False
    FakeOtpProvider.fail_verify = False


def auth_response(client, id_token="valid-token"):
    return client.post("/api/v1/auth/firebase/", {"id_token": id_token}, format="json")


@pytest.mark.django_db
def test_first_login_creates_customer():
    response = auth_response(APIClient())

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] is True
    assert payload["user"]["phone_number"] == "+919876543210"
    assert payload["user"]["role"] == UserRole.CUSTOMER
    assert payload["user"]["is_verified"] is True
    assert payload["tokens"]["token_type"] == "Bearer"
    assert payload["tokens"]["access"]
    assert payload["tokens"]["refresh"]
    assert User.objects.count() == 1
    assert CustomerProfile.objects.count() == 1


@pytest.mark.django_db
def test_repeated_login_returns_existing_customer():
    client = APIClient()
    first = auth_response(client)
    second = auth_response(client)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert User.objects.count() == 1
    assert CustomerProfile.objects.count() == 1


@pytest.mark.django_db
def test_invalid_firebase_token():
    FakeProvider.error = FirebaseTokenError("Invalid Firebase ID token.")

    response = auth_response(APIClient(), id_token="bad-token")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_missing_phone_claim():
    FakeProvider.phone_number = ""

    response = auth_response(APIClient())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_otp_send_uses_backend_provider():
    response = APIClient().post("/api/v1/auth/otp/send/", {"phone_number": "+919629025814"}, format="json")

    assert response.status_code == 200
    assert response.json()["phone_number"] == "+919629025814"
    assert response.json()["request_id"] == "otp-request-id"
    assert FakeOtpProvider.sent_mobile == "919629025814"


@pytest.mark.django_db
def test_otp_verify_creates_customer_session():
    response = APIClient().post(
        "/api/v1/auth/otp/verify/",
        {"phone_number": "+919629025814", "otp": "123456"},
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["phone_number"] == "+919629025814"
    assert payload["tokens"]["access"]
    assert payload["tokens"]["refresh"]
    assert FakeOtpProvider.verified_mobile == "919629025814"
    assert FakeOtpProvider.verified_otp == "123456"


@pytest.mark.django_db
def test_otp_verify_rejects_provider_failure():
    FakeOtpProvider.fail_verify = True

    response = APIClient().post(
        "/api/v1/auth/otp/verify/",
        {"phone_number": "+919629025814", "otp": "123456"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_password_signup_creates_customer_session():
    response = APIClient().post(
        "/api/v1/auth/password/signup/",
        {
            "phone_number": "+919629025814",
            "password": "StrongPass123",
            "first_name": "Viknesh",
            "email": "viknesh@example.com",
        },
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    user = User.objects.get(phone_number="+919629025814")
    assert payload["created"] is True
    assert payload["user"]["first_name"] == "Viknesh"
    assert payload["user"]["role"] == UserRole.CUSTOMER
    assert payload["tokens"]["access"]
    assert user.check_password("StrongPass123") is True
    assert CustomerProfile.objects.filter(user=user).exists() is True


@pytest.mark.django_db
def test_password_signup_rejects_existing_password_account():
    User.objects.create_user(phone_number="+919629025814", password="StrongPass123", role=UserRole.CUSTOMER)

    response = APIClient().post(
        "/api/v1/auth/password/signup/",
        {"phone_number": "+919629025814", "password": "NewStrongPass123"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_password_signup_does_not_modify_admin_accounts():
    User.objects.create_user(
        phone_number="+919629025814",
        role=UserRole.ADMIN,
        is_staff=True,
        is_verified=True,
    )

    response = APIClient().post(
        "/api/v1/auth/password/signup/",
        {"phone_number": "+919629025814", "password": "StrongPass123"},
        format="json",
    )

    user = User.objects.get(phone_number="+919629025814")
    assert response.status_code == 400
    assert user.has_usable_password() is False


@pytest.mark.django_db
def test_password_login_returns_customer_session():
    User.objects.create_user(
        phone_number="+919629025814",
        password="StrongPass123",
        role=UserRole.CUSTOMER,
        is_verified=True,
    )

    response = APIClient().post(
        "/api/v1/auth/password/login/",
        {"phone_number": "+919629025814", "password": "StrongPass123"},
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] is False
    assert payload["user"]["phone_number"] == "+919629025814"
    assert payload["tokens"]["access"]


@pytest.mark.django_db
def test_password_login_rejects_bad_credentials():
    User.objects.create_user(phone_number="+919629025814", password="StrongPass123", role=UserRole.CUSTOMER)

    response = APIClient().post(
        "/api/v1/auth/password/login/",
        {"phone_number": "+919629025814", "password": "WrongPass123"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_disabled_user_cannot_login():
    User.objects.create_user(
        phone_number="+919876543210",
        role=UserRole.CUSTOMER,
        is_verified=True,
        is_active=False,
    )

    response = auth_response(APIClient())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_authentication_required_for_me():
    response = APIClient().get("/api/v1/auth/me/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_me_returns_authenticated_user():
    client = APIClient()
    login = auth_response(client).json()

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['tokens']['access']}")
    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    assert response.json()["phone_number"] == "+919876543210"


@pytest.mark.django_db
def test_me_updates_customer_profile_fields():
    client = APIClient()
    login = auth_response(client).json()

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['tokens']['access']}")
    response = client.patch(
        "/api/v1/auth/me/",
        {
            "first_name": "Viknesh",
            "last_name": "B",
            "email": "viknesh@example.com",
            "display_name": "Viknesh",
            "alternate_phone": "+919629025814",
            "role": "ADMIN",
        },
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["first_name"] == "Viknesh"
    assert payload["last_name"] == "B"
    assert payload["email"] == "viknesh@example.com"
    assert payload["role"] == UserRole.CUSTOMER
    assert payload["customer_profile"]["display_name"] == "Viknesh"
    assert payload["customer_profile"]["alternate_phone"] == "+919629025814"


@pytest.mark.django_db
def test_refresh_returns_new_access_token():
    client = APIClient()
    login = auth_response(client).json()

    response = client.post(
        "/api/v1/auth/refresh/",
        {"refresh": login["tokens"]["refresh"]},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["access"]


@pytest.mark.django_db
def test_logout_blacklists_refresh_token():
    client = APIClient()
    login = auth_response(client).json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['tokens']['access']}")

    logout = client.post(
        "/api/v1/auth/logout/",
        {"refresh": login["tokens"]["refresh"]},
        format="json",
    )
    refresh = client.post(
        "/api/v1/auth/refresh/",
        {"refresh": login["tokens"]["refresh"]},
        format="json",
    )

    assert logout.status_code == 204
    assert refresh.status_code == 401


def test_role_permissions():
    from apps.accounts.permissions import IsAdminRole

    class Request:
        user = type("User", (), {"is_authenticated": True, "role": UserRole.CUSTOMER})()

    assert IsAdminRole().has_permission(Request(), None) is False

    Request.user.role = UserRole.ADMIN
    assert IsAdminRole().has_permission(Request(), None) is True


@pytest.mark.django_db
def test_dev_phone_login_disabled_by_default():
    response = APIClient().post("/api/v1/auth/dev-phone/", {"phone_number": "+919629025814"}, format="json")

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=True, DEV_PHONE_LOGIN_ENABLED=True, DEV_PHONE_LOGIN_ALLOWED_NUMBERS=["+919629025814"])
def test_dev_phone_login_creates_allowed_customer():
    response = APIClient().post("/api/v1/auth/dev-phone/", {"phone_number": "+919629025814"}, format="json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["phone_number"] == "+919629025814"
    assert payload["user"]["role"] == UserRole.CUSTOMER
    assert payload["user"]["is_verified"] is True
    assert payload["tokens"]["access"]
    assert payload["tokens"]["refresh"]


@pytest.mark.django_db
def test_ensure_superuser_command_creates_or_updates_admin(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PHONE_NUMBER", "+919999999999")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "strong-test-password")
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")

    call_command("ensure_superuser")
    call_command("ensure_superuser")

    user = User.objects.get(phone_number="+919999999999")
    assert user.email == "admin@example.com"
    assert user.role == UserRole.SUPER_ADMIN
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.is_verified is True
    assert user.check_password("strong-test-password") is True
