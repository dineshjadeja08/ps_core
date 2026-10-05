from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.scheduling.models import TimeSlot
from apps.technicians.models import (
    TechnicianAssignment,
    TechnicianAvailabilityStatus,
    TechnicianLeave,
    TechnicianProfile,
    TechnicianSkill,
    TechnicianVerificationStatus,
    TechnicianWorkingHours,
)


@pytest.fixture
def customer():
    return User.objects.create_user("+919876543210", role=UserRole.CUSTOMER, is_verified=True)


@pytest.fixture
def admin_user():
    return User.objects.create_user("+919876543299", role=UserRole.ADMIN, is_verified=True, is_staff=True)


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def customer_client(customer):
    client = APIClient()
    client.force_authenticate(user=customer)
    return client


@pytest.fixture
def service_area():
    return ServiceArea.objects.create(
        name="Tirupattur Central",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )


@pytest.fixture
def booking(customer, service_area):
    category = ServiceCategory.objects.create(name="AC Service", slug="ac-service")
    service = Service.objects.create(
        category=category,
        name="AC General Service",
        slug="ac-general-service",
        base_price=Decimal("1499.00"),
        advance_amount=Decimal("299.00"),
        estimated_duration_minutes=90,
    )
    address = Address.objects.create(
        customer=customer,
        label="Home",
        recipient_name="Dinesh",
        phone="+919876543210",
        address_line_1="12 Main Road",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )
    slot = TimeSlot.objects.create(
        service_area=service_area,
        date=timezone.localdate() + timedelta(days=1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        capacity=2,
    )
    return Booking.objects.create(
        booking_number="PS-TECH01",
        customer=customer,
        service=service,
        address=address,
        address_snapshot={"postal_code": "635601"},
        service_date=slot.date,
        time_slot=slot,
        problem_description="AC is not cooling.",
        subtotal=Decimal("1499.00"),
        total_amount=Decimal("1499.00"),
        advance_required=Decimal("299.00"),
        advance_paid=Decimal("299.00"),
        balance_due=Decimal("1200.00"),
        booking_status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.PARTIALLY_PAID,
    )


def create_technician(*, code="TECH-001", phone="+919876543300", active=True, service_area=None, service=None):
    user = User.objects.create_user(phone, role=UserRole.TECHNICIAN, is_verified=True)
    skill = TechnicianSkill.objects.create(name=f"AC Skill {code}")
    profile = TechnicianProfile.objects.create(
        user=user,
        employee_code=code,
        display_name=f"Technician {code}",
        phone=phone,
        is_active=active,
        is_available=True,
        background_verification_status=TechnicianVerificationStatus.VERIFIED if active else TechnicianVerificationStatus.PENDING,
        availability_status=TechnicianAvailabilityStatus.AVAILABLE,
    )
    profile.skills.add(skill)
    if service_area:
        profile.service_areas.add(service_area)
    if service:
        profile.supported_services.add(service)
    return profile


@pytest.mark.django_db
def test_admin_can_create_and_edit_technician_with_coverage(admin_client, booking, service_area, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post("/api/v1/admin/technicians/", {
            "employee_code": "NEW-001", "display_name": "New technician", "phone": "+919876540001",
            "skill_names": ["AC repair", "AC repair"], "service_area_ids": [str(service_area.id)],
            "supported_service_ids": [str(booking.service_id)], "internal_notes": "Onboarded",
        }, format="json")
    assert response.status_code == 201, response.data
    technician = TechnicianProfile.objects.get(pk=response.data["id"])
    assert technician.user.role == UserRole.TECHNICIAN
    assert not technician.user.has_usable_password()
    assert technician.skills.count() == 1
    assert technician.service_areas.get() == service_area
    assert technician.supported_services.get() == booking.service
    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {
            "phone": "+919876540002", "availability_status": "BUSY", "internal_notes": "Next visit later",
        }, format="json")
    assert response.status_code == 200, response.data
    technician.refresh_from_db()
    technician.user.refresh_from_db()
    assert technician.user.phone_number == "+919876540002"
    assert not technician.is_available
    assert technician.is_active
    from apps.audit.models import AuditLog
    assert AuditLog.objects.filter(resource_type="technician", resource_id=str(technician.id)).count() == 2


@pytest.mark.django_db
def test_create_never_converts_customer_account_to_technician(admin_client, customer):
    response = admin_client.post("/api/v1/admin/technicians/", {
        "employee_code": "BAD-001", "display_name": "Not allowed", "phone": customer.phone_number,
    }, format="json")
    assert response.status_code == 400
    customer.refresh_from_db()
    assert customer.role == UserRole.CUSTOMER
    assert not TechnicianProfile.objects.filter(user=customer).exists()


@pytest.mark.django_db
def test_edit_rejects_another_accounts_phone(admin_client, customer):
    technician = create_technician()
    response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"phone": customer.phone_number}, format="json")
    assert response.status_code == 400
    technician.refresh_from_db()
    assert technician.phone != customer.phone_number


@pytest.mark.django_db
def test_phone_change_unlinks_old_firebase_identity(admin_client):
    technician = create_technician()
    technician.user.firebase_uid = "old-phone-identity"
    technician.user.save()
    response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"phone": "+919876540099"}, format="json")
    assert response.status_code == 200
    technician.user.refresh_from_db()
    assert technician.user.firebase_uid is None
    assert not technician.user.is_verified


@pytest.mark.django_db
def test_suspended_active_profile_is_rejected_and_inactive_employment_blocks_assignment(admin_client, booking):
    technician = create_technician()
    response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"availability_status": "SUSPENDED"}, format="json")
    assert response.status_code == 400
    technician.refresh_from_db()
    assert technician.availability_status == TechnicianAvailabilityStatus.AVAILABLE
    response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"employment_status": "LEFT"}, format="json")
    assert response.status_code == 200
    assert not response.data["is_active"]
    assert not response.data["is_available"]
    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/assign-technician/", {"technician_id": str(technician.id)}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_invalid_coverage_does_not_create_a_login_account(admin_client):
    response = admin_client.post("/api/v1/admin/technicians/", {
        "employee_code": "BAD-COVERAGE", "display_name": "Invalid", "phone": "+919876540098",
        "service_area_ids": ["00000000-0000-0000-0000-000000000000"],
    }, format="json")
    assert response.status_code == 400
    assert not User.objects.filter(phone_number="+919876540098").exists()


@pytest.mark.django_db
def test_deactivate_preserves_bookings_and_allows_reactivation(admin_client, booking):
    technician = create_technician()
    assert admin_client.post(f"/api/v1/admin/bookings/{booking.id}/assign-technician/", {"technician_id": str(technician.id)}, format="json").status_code == 200
    response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"is_active": False}, format="json")
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.assigned_technician_id == technician.user_id
    assert TechnicianAssignment.objects.filter(technician=technician).exists()
    assert not admin_client.get("/api/v1/admin/technicians/").data
    assert len(admin_client.get("/api/v1/admin/technicians/?include_inactive=true").data) == 1
    assert admin_client.get(f"/api/v1/admin/technicians/{technician.id}/").status_code == 200
    assert admin_client.delete(f"/api/v1/admin/technicians/{technician.id}/").status_code == 405
    response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"is_active": True, "availability_status": "AVAILABLE"}, format="json")
    assert response.status_code == 200
    assert response.data["is_available"]


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["BUSY", "ON_LEAVE", "OFFLINE"])
def test_availability_controls_eligibility_without_changing_job_status(admin_client, booking, status):
    technician = create_technician()
    response = admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"availability_status": status}, format="json")
    assert response.status_code == 200
    assert not response.data["is_available"]
    assert response.data["is_active"]
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.CONFIRMED
    response = admin_client.get(f"/api/v1/admin/technicians/?booking_id={booking.id}&include_ineligible=true")
    assert "not available" in str(response.data[0]["eligibility_errors"])
    assert not admin_client.get(f"/api/v1/admin/technicians/?booking_id={booking.id}").data


@pytest.mark.django_db
def test_technician_filters_and_assignment_reasons(admin_client, booking, service_area):
    eligible = create_technician(service_area=service_area, service=booking.service)
    unavailable = create_technician(code="OTHER-001", phone="+919876540003", service=booking.service)
    unavailable.availability_status = TechnicianAvailabilityStatus.BUSY
    unavailable.save()
    response = admin_client.get("/api/v1/admin/technicians/", {"search": eligible.employee_code, "service_id": str(booking.service_id), "area_id": str(service_area.id), "availability_status": "AVAILABLE"})
    assert [item["id"] for item in response.data] == [str(eligible.id)]
    response = admin_client.get("/api/v1/admin/technicians/", {"booking_id": str(booking.id), "include_ineligible": "true"})
    assert len(response.data) == 2
    assert any(item["eligibility_errors"] for item in response.data)
    assert admin_client.get("/api/v1/admin/technicians/?area_id=bad-id").status_code == 400
    assert admin_client.get("/api/v1/admin/technicians/?booking_id=bad-id").status_code == 400


@pytest.mark.django_db
def test_technician_jobs_counts_and_approved_ratings_are_scoped(admin_client, booking, customer):
    from apps.reviews.models import Review
    technician = create_technician()
    other = create_technician(code="OTHER-001", phone="+919876540003")
    booking.assigned_technician = technician.user
    booking.save()
    response = admin_client.get(f"/api/v1/admin/technicians/{technician.id}/jobs/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert admin_client.get(f"/api/v1/admin/technicians/{other.id}/jobs/").data["count"] == 0
    booking.booking_status = BookingStatus.TECHNICIAN_ASSIGNED
    booking.save()
    response = admin_client.get(f"/api/v1/admin/technicians/{technician.id}/")
    assert response.data["active_job_count"] == 1
    booking.booking_status = BookingStatus.COMPLETED
    booking.save()
    Review.objects.create(booking=booking, customer=customer, technician=technician.user, rating=4, comment="Good", is_visible=True)
    Review.objects.create(service=booking.service, reviewer_name="Hidden", technician=technician.user, rating=1, comment="Hidden", is_visible=False)
    response = admin_client.get(f"/api/v1/admin/technicians/{technician.id}/")
    assert response.data["active_job_count"] == 0
    assert response.data["completed_jobs"] == 1
    assert response.data["approved_review_count"] == 1
    assert response.data["approved_rating"] == "4.00"
    assert admin_client.get(f"/api/v1/admin/technicians/{technician.id}/jobs/?active=true").data["count"] == 0


@pytest.mark.django_db
def test_technician_activity_hides_unrelated_and_sensitive_metadata(admin_client, admin_user):
    from apps.audit.models import AuditAction, AuditLog
    technician = create_technician()
    AuditLog.objects.create(actor=admin_user, action=AuditAction.TECHNICIAN_UPDATED, resource_type="technician", resource_id=str(technician.id), metadata={"availability": "BUSY", "secret": "do-not-expose"})
    AuditLog.objects.create(actor=admin_user, action=AuditAction.TECHNICIAN_UPDATED, resource_type="technician", resource_id="other", metadata={"availability": "SUSPENDED"})
    response = admin_client.get(f"/api/v1/admin/technicians/{technician.id}/activities/")
    assert response.status_code == 200
    assert len(response.data) == 2
    assert "BUSY" in str(response.data)
    assert "SUSPENDED" not in str(response.data)
    assert "do-not-expose" not in str(response.data)


@pytest.mark.django_db
def test_customer_cannot_manage_technicians(customer_client):
    technician = create_technician()
    for suffix in ["", "options/", f"{technician.id}/", f"{technician.id}/jobs/", f"{technician.id}/activities/"]:
        assert customer_client.get(f"/api/v1/admin/technicians/{suffix}").status_code == 403
    assert customer_client.post("/api/v1/admin/technicians/", {}, format="json").status_code == 403
    assert customer_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"is_active": False}, format="json").status_code == 403


@pytest.mark.django_db
def test_coordinator_can_manage_profile_and_coverage_options(admin_client, admin_user, booking, service_area):
    from django.contrib.auth.models import Group
    admin_user.groups.add(Group.objects.get_or_create(name="Technician Coordinator")[0])
    assert admin_client.get("/api/v1/admin/technicians/options/").status_code == 200
    technician = create_technician(service_area=service_area, service=booking.service)
    assert admin_client.patch(f"/api/v1/admin/technicians/{technician.id}/", {"internal_notes": "Dispatch"}, format="json").status_code == 200
    assert admin_client.get(f"/api/v1/admin/technicians/{technician.id}/jobs/").status_code == 200


@pytest.mark.django_db
def test_home_pincode_does_not_override_explicit_coverage(admin_client, booking, service_area):
    technician = create_technician(service_area=service_area, service=booking.service)
    technician.pincode = "600040"
    technician.save()
    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/assign-technician/", {"technician_id": str(technician.id)}, format="json")
    assert response.status_code == 200


@pytest.mark.django_db
def test_configured_hours_reject_unscheduled_day(admin_client, booking):
    technician = create_technician()
    TechnicianWorkingHours.objects.create(technician=technician, day_of_week=(booking.service_date.weekday() + 1) % 7, start_time=time(9), end_time=time(18))
    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/assign-technician/", {"technician_id": str(technician.id)}, format="json")
    assert response.status_code == 400
    assert "not working" in str(response.data)


@pytest.mark.django_db
def test_admin_assignment(admin_client, booking, service_area):
    technician = create_technician(service_area=service_area)

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id), "notes": "Manual dispatch."},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.assigned_technician_id == technician.user_id
    assert booking.booking_status == BookingStatus.TECHNICIAN_ASSIGNED
    assert TechnicianAssignment.objects.count() == 1


@pytest.mark.django_db
def test_technician_portal_lists_only_assigned_jobs_and_updates_progress(booking, service_area):
    technician = create_technician(service_area=service_area)
    booking.assigned_technician = technician.user
    booking.booking_status = BookingStatus.TECHNICIAN_ASSIGNED
    booking.save(update_fields=["assigned_technician", "booking_status", "updated_at"])
    client = APIClient()
    client.force_authenticate(user=technician.user)

    listed = client.get("/api/v1/technician/jobs/")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["results"][0]["customer_phone"] == booking.customer.phone_number

    en_route = client.post(f"/api/v1/technician/jobs/{booking.id}/en-route/", {}, format="json")
    assert en_route.status_code == 200
    assert en_route.json()["booking_status"] == BookingStatus.TECHNICIAN_EN_ROUTE

    started = client.post(f"/api/v1/technician/jobs/{booking.id}/start/", {}, format="json")
    assert started.status_code == 200
    assert started.json()["booking_status"] == BookingStatus.IN_PROGRESS


@pytest.mark.django_db
def test_technician_cannot_access_another_technicians_job(booking, service_area):
    assigned = create_technician(code="TECH-A", phone="+919876543301", service_area=service_area)
    other = create_technician(code="TECH-B", phone="+919876543302", service_area=service_area)
    booking.assigned_technician = assigned.user
    booking.booking_status = BookingStatus.TECHNICIAN_ASSIGNED
    booking.save(update_fields=["assigned_technician", "booking_status", "updated_at"])
    client = APIClient()
    client.force_authenticate(user=other.user)

    response = client.post(f"/api/v1/technician/jobs/{booking.id}/start/", {}, format="json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_customer_forbidden(customer_client, booking, service_area):
    technician = create_technician(service_area=service_area)

    response = customer_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_inactive_technician(admin_client, booking, service_area):
    technician = create_technician(active=False, service_area=service_area)

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_reassignment(admin_client, booking, service_area):
    first = create_technician(code="TECH-001", phone="+919876543301", service_area=service_area)
    second = create_technician(code="TECH-002", phone="+919876543302", service_area=service_area)

    admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(first.id)},
        format="json",
    )
    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(second.id), "notes": "Reassigned."},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.assigned_technician_id == second.user_id
    assert TechnicianAssignment.objects.filter(unassigned_at__isnull=False).count() == 1
    assert TechnicianAssignment.objects.filter(unassigned_at__isnull=True, technician=second).count() == 1


@pytest.mark.django_db
def test_assignment_history(admin_client, booking, service_area, admin_user):
    technician = create_technician(service_area=service_area)

    admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id), "notes": "History note."},
        format="json",
    )

    assignment = TechnicianAssignment.objects.get()
    assert assignment.booking == booking
    assert assignment.technician == technician
    assert assignment.assigned_by == admin_user
    assert assignment.notes == "History note."


@pytest.mark.django_db
def test_booking_status_transition(admin_client, booking, service_area):
    technician = create_technician(service_area=service_area)

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["booking_status"] == BookingStatus.TECHNICIAN_ASSIGNED


@pytest.mark.django_db
def test_assignment_requires_verified_technician(admin_client, booking, service_area):
    technician = create_technician(service_area=service_area)
    technician.background_verification_status = TechnicianVerificationStatus.UNDER_REVIEW
    technician.save()

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 400
    assert "Technician is not verified." in str(response.json())


@pytest.mark.django_db
def test_assignment_rejects_unsupported_service(admin_client, booking, service_area):
    category = ServiceCategory.objects.create(name="Cleaning", slug="cleaning")
    other_service = Service.objects.create(
        category=category,
        name="Bathroom Cleaning",
        slug="bathroom-cleaning",
        base_price=Decimal("999.00"),
        advance_amount=Decimal("199.00"),
        estimated_duration_minutes=60,
    )
    technician = create_technician(service_area=service_area, service=other_service)

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 400
    assert "does not support this service" in str(response.json())


@pytest.mark.django_db
def test_assignment_rejects_non_working_hours(admin_client, booking, service_area):
    technician = create_technician(service_area=service_area, service=booking.service)
    TechnicianWorkingHours.objects.create(
        technician=technician,
        day_of_week=booking.service_date.weekday(),
        start_time=time(13, 0),
        end_time=time(18, 0),
    )

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 400
    assert "not working during this slot" in str(response.json())


@pytest.mark.django_db
def test_assignment_rejects_technician_on_leave(admin_client, booking, service_area):
    technician = create_technician(service_area=service_area, service=booking.service)
    slot_start = timezone.make_aware(
        timezone.datetime.combine(booking.service_date, booking.time_slot.start_time),
        timezone.get_current_timezone(),
    )
    TechnicianLeave.objects.create(
        technician=technician,
        start_at=slot_start - timedelta(minutes=30),
        end_at=slot_start + timedelta(hours=3),
        reason="Personal leave",
    )

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 400
    assert "on leave" in str(response.json())


@pytest.mark.django_db
def test_assignment_rejects_overlapping_booking(admin_client, booking, service_area, customer):
    technician = create_technician(service_area=service_area, service=booking.service)
    first_response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )
    assert first_response.status_code == 200

    other_booking = Booking.objects.create(
        booking_number="PS-TECH02",
        customer=customer,
        service=booking.service,
        address=booking.address,
        address_snapshot={"postal_code": "635601"},
        service_date=booking.service_date,
        time_slot=booking.time_slot,
        problem_description="Another visit.",
        subtotal=Decimal("1499.00"),
        total_amount=Decimal("1499.00"),
        advance_required=Decimal("299.00"),
        advance_paid=Decimal("299.00"),
        balance_due=Decimal("1200.00"),
        booking_status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.PARTIALLY_PAID,
    )

    response = admin_client.post(
        f"/api/v1/admin/bookings/{other_booking.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 400
    assert "overlapping booking" in str(response.json())


@pytest.mark.django_db
def test_admin_technician_list_can_filter_eligible_by_booking(admin_client, booking, service_area):
    eligible = create_technician(code="TECH-ELIG", phone="+919876543303", service_area=service_area, service=booking.service)
    other_area = ServiceArea.objects.create(
        name="Other Area",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635602",
    )
    create_technician(code="TECH-BAD", phone="+919876543304", service_area=other_area, service=booking.service)

    response = admin_client.get(f"/api/v1/admin/technicians/?booking_id={booking.id}")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert str(eligible.id) in ids
    assert len(ids) == 1


@pytest.mark.django_db
def test_remove_assignment_preserves_assignment_history(admin_client, booking, service_area):
    technician = create_technician(service_area=service_area, service=booking.service)
    admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id), "reason": "Nearest technician"},
        format="json",
    )

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/remove-technician/",
        {"notes": "Technician called in sick."},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    assignment = TechnicianAssignment.objects.get()
    assert booking.assigned_technician is None
    assert booking.booking_status == BookingStatus.CONFIRMED
    assert assignment.unassigned_at is not None
    assert "called in sick" in assignment.notes
