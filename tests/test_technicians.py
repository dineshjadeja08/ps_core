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
