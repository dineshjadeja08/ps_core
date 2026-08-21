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
from apps.technicians.models import TechnicianAssignment, TechnicianProfile, TechnicianSkill


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


def create_technician(*, code="TECH-001", phone="+919876543300", active=True, service_area=None):
    user = User.objects.create_user(phone, role=UserRole.TECHNICIAN, is_verified=True)
    skill = TechnicianSkill.objects.create(name=f"AC Skill {code}")
    profile = TechnicianProfile.objects.create(
        user=user,
        employee_code=code,
        display_name=f"Technician {code}",
        phone=phone,
        is_active=active,
        is_available=True,
    )
    profile.skills.add(skill)
    if service_area:
        profile.service_areas.add(service_area)
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
