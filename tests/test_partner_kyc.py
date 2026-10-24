from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.technicians.models import TechnicianCompanyUser, TechnicianProfile, TechnicianSkill, TechnicianVerificationStatus
from tests.factories import user_factory

pytestmark = pytest.mark.django_db


@pytest.fixture
def firebase_phone(monkeypatch):
    phone = SimpleNamespace(value="+919811112222")
    monkeypatch.setattr(
        "apps.accounts.services.get_firebase_auth_provider",
        lambda: SimpleNamespace(verify_id_token=lambda token: SimpleNamespace(phone_number=phone.value, uid="uid")),
    )
    return phone


def _signup(app="partner"):
    return APIClient().post("/api/v1/auth/firebase/", {"id_token": "token", "app": app}, format="json")


def _client_for(phone):
    client = APIClient()
    client.force_authenticate(user=User.objects.get(phone_number=phone))
    return client


def _file(name="doc.png"):
    return SimpleUploadedFile(name, b"\x89PNG\r\n\x1a\n" + b"0" * 64, content_type="image/png")


def test_partner_app_requires_company_invitation(firebase_phone):
    denied = _signup()
    assert denied.status_code == 400
    assert "not invited" in str(denied.json()).lower()

    vendor_user = user_factory(firebase_phone.value, role=UserRole.TECHNICIAN)
    vendor = TechnicianProfile.objects.create(
        user=vendor_user, employee_code="PSP-INVITED", display_name="Invited vendor",
        phone=vendor_user.phone_number, technician_type="PARTNER",
        background_verification_status=TechnicianVerificationStatus.PENDING,
        is_available=False,
    )
    invited_user = user_factory("+919811112223", role=UserRole.TECHNICIAN, is_verified=False)
    TechnicianCompanyUser.objects.create(technician=vendor, user=invited_user)
    firebase_phone.value = invited_user.phone_number

    response = _signup()

    assert response.status_code == 200
    assert response.json()["user"]["role"] == UserRole.TECHNICIAN
    assert TechnicianProfile.objects.filter(user__phone_number=invited_user.phone_number).count() == 0
    assert _client_for(invited_user.phone_number).get("/api/v1/technician/profile/").json()["id"] == str(vendor.id)


def test_customer_app_login_still_creates_customers(firebase_phone):
    assert _signup(app="customer").json()["user"]["role"] == UserRole.CUSTOMER


def test_customer_number_cannot_sign_up_as_partner(firebase_phone):
    user_factory(firebase_phone.value)

    response = _signup()

    assert response.status_code == 400
    assert "registered as a Purple Squad customer" in str(response.json())


def test_full_kyc_flow_submit_then_admin_approves(firebase_phone, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    from apps.technicians.services import create_partner_signup

    create_partner_signup(user_factory(firebase_phone.value, role=UserRole.TECHNICIAN, is_verified=False))
    _signup()
    client = _client_for(firebase_phone.value)
    skill = TechnicianSkill.objects.create(name="AC repair")

    incomplete = client.post("/api/v1/technician/kyc/submit/")
    assert incomplete.status_code == 400
    assert "PAN card" in str(incomplete.json())

    assert client.get("/api/v1/technician/skills/").json()[0]["name"] == "AC repair"
    updated = client.patch("/api/v1/technician/profile/", {"display_name": "Ravi Kumar", "city": "Bengaluru", "pincode": "560102", "skill_ids": [str(skill.id)], "experience_years": "4"}, format="json")
    assert updated.status_code == 200 and updated.json()["skills"][0]["name"] == "AC repair"
    for doc_type in ("AADHAAR_FRONT", "AADHAAR_BACK", "PAN", "PHOTO"):
        assert client.post("/api/v1/technician/documents/", {"doc_type": doc_type, "file": _file()}, format="multipart").status_code == 201
    replaced = client.post("/api/v1/technician/documents/", {"doc_type": "PAN", "file": _file("pan2.png")}, format="multipart")
    assert replaced.status_code == 201
    assert len(client.get("/api/v1/technician/documents/").json()) == 4

    submitted = client.post("/api/v1/technician/kyc/submit/")
    assert submitted.status_code == 200
    assert submitted.json()["background_verification_status"] == "UNDER_REVIEW"
    locked = client.patch("/api/v1/technician/profile/", {"city": "Chennai"}, format="json")
    assert locked.status_code == 400

    admin = APIClient()
    admin.force_authenticate(user=user_factory("+919800000001", role=UserRole.ADMIN, is_staff=True))
    profile = TechnicianProfile.objects.get(user__phone_number=firebase_phone.value)
    pending = admin.get("/api/v1/admin/technicians/?verification=UNDER_REVIEW").json()
    assert [row["id"] for row in pending] == [str(profile.id)]
    assert len(admin.get(f"/api/v1/admin/technicians/{profile.id}/kyc/").json()["documents"]) == 4
    approved = admin.post(f"/api/v1/admin/technicians/{profile.id}/kyc/", {"decision": "APPROVE"}, format="json")

    assert approved.status_code == 200
    profile.refresh_from_db()
    assert profile.background_verification_status == TechnicianVerificationStatus.VERIFIED
    assert profile.is_available and profile.profile_photo


def test_admin_rejection_needs_note_and_lets_partner_fix(firebase_phone, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    from apps.technicians.services import create_partner_signup

    create_partner_signup(user_factory(firebase_phone.value, role=UserRole.TECHNICIAN, is_verified=False))
    _signup()
    profile = TechnicianProfile.objects.get(user__phone_number=firebase_phone.value)
    profile.background_verification_status = TechnicianVerificationStatus.UNDER_REVIEW
    profile.save()
    admin = APIClient()
    admin.force_authenticate(user=user_factory("+919800000002", role=UserRole.ADMIN, is_staff=True))

    no_note = admin.post(f"/api/v1/admin/technicians/{profile.id}/kyc/", {"decision": "REJECT"}, format="json")
    rejected = admin.post(f"/api/v1/admin/technicians/{profile.id}/kyc/", {"decision": "REJECT", "note": "PAN photo is blurry."}, format="json")
    partner = _client_for(firebase_phone.value)

    assert no_note.status_code == 400
    assert rejected.json()["verification_note"] == "PAN photo is blurry."
    assert partner.get("/api/v1/technician/profile/").json()["background_verification_status"] == "REJECTED"
    assert partner.post("/api/v1/technician/documents/", {"doc_type": "PAN", "file": _file()}, format="multipart").status_code == 201


def test_sync_technician_skills_adds_missing_categories_only():
    from django.core.management import call_command

    from apps.catalogue.models import ServiceCategory

    ServiceCategory.objects.create(name="AC Service", slug="ac-service")
    ServiceCategory.objects.create(name="Plumbing", slug="plumbing")
    ServiceCategory.objects.create(name="Retired", slug="retired", is_active=False)
    existing = TechnicianSkill.objects.create(name="ac service", description="kept as is")

    call_command("sync_technician_skills")
    call_command("sync_technician_skills")

    assert sorted(TechnicianSkill.objects.values_list("name", flat=True)) == ["Plumbing", "ac service"]
    existing.refresh_from_db()
    assert existing.description == "kept as is"
