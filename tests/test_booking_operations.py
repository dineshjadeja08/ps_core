from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType
from apps.scheduling.models import TimeSlot


@pytest.fixture
def customer():
    return User.objects.create_user("+919876543210", role=UserRole.CUSTOMER, is_verified=True)


@pytest.fixture
def admin_user():
    return User.objects.create_user("+919876543299", role=UserRole.ADMIN, is_verified=True, is_staff=True)


@pytest.fixture
def technician_user():
    return User.objects.create_user("+919876543300", role=UserRole.TECHNICIAN, is_verified=True)


@pytest.fixture
def customer_client(customer):
    client = APIClient()
    client.force_authenticate(user=customer)
    return client


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
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
def service():
    category = ServiceCategory.objects.create(name="AC Service", slug="ac-service")
    return Service.objects.create(
        category=category,
        name="AC General Service",
        slug="ac-general-service",
        base_price=Decimal("1499.00"),
        advance_amount=Decimal("299.00"),
        estimated_duration_minutes=90,
    )


@pytest.fixture
def address(customer):
    return Address.objects.create(
        customer=customer,
        label="Home",
        recipient_name="Dinesh",
        phone="+919876543210",
        address_line_1="12 Main Road",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )


def create_slot(service_area, *, days=2, start_hour=10):
    return TimeSlot.objects.create(
        service_area=service_area,
        date=timezone.localdate() + timedelta(days=days),
        start_time=time(start_hour, 0),
        end_time=time(start_hour + 2, 0),
        capacity=2,
    )


def create_booking(customer, service, address, slot, **overrides):
    data = {
        "booking_number": f"PS-OPS{Booking.objects.count() + 1:03d}",
        "customer": customer,
        "service": service,
        "address": address,
        "address_snapshot": {"postal_code": address.postal_code},
        "service_date": slot.date,
        "time_slot": slot,
        "problem_description": "AC is not cooling.",
        "subtotal": Decimal("1499.00"),
        "total_amount": Decimal("1499.00"),
        "advance_required": Decimal("299.00"),
        "advance_paid": Decimal("299.00"),
        "balance_due": Decimal("1200.00"),
        "booking_status": BookingStatus.CONFIRMED,
        "payment_status": PaymentStatus.PARTIALLY_PAID,
    }
    data.update(overrides)
    return Booking.objects.create(**data)


@pytest.mark.django_db
def test_admin_start_requires_assigned_technician(admin_client, customer, service, address, service_area):
    booking = create_booking(customer, service, address, create_slot(service_area))

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/start/", {}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_admin_start_valid_transition(admin_client, customer, service, address, service_area, technician_user):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area),
        booking_status=BookingStatus.TECHNICIAN_ASSIGNED,
        assigned_technician=technician_user,
    )

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/start/", {"notes": "Arrived."}, format="json")

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.IN_PROGRESS
    assert BookingStatusHistory.objects.filter(to_status=BookingStatus.IN_PROGRESS, notes="Arrived.").exists()


@pytest.mark.django_db
def test_admin_complete_requires_in_progress(admin_client, customer, service, address, service_area, technician_user):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area),
        booking_status=BookingStatus.TECHNICIAN_ASSIGNED,
        assigned_technician=technician_user,
        balance_collected=Decimal("1200.00"),
    )

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/complete/", {}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_admin_complete_requires_balance(admin_client, customer, service, address, service_area, technician_user):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area),
        booking_status=BookingStatus.IN_PROGRESS,
        assigned_technician=technician_user,
        balance_collected=Decimal("100.00"),
    )

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/complete/", {}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_admin_complete_valid_transition(admin_client, customer, service, address, service_area, technician_user):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area),
        booking_status=BookingStatus.IN_PROGRESS,
        assigned_technician=technician_user,
        balance_collected=Decimal("1200.00"),
        payment_status=PaymentStatus.PAID,
    )

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/complete/", {}, format="json")

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.COMPLETED
    assert booking.completed_at is not None


@pytest.mark.django_db
def test_record_balance_creates_payment_audit(admin_client, customer, service, address, service_area, technician_user):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area),
        booking_status=BookingStatus.IN_PROGRESS,
        assigned_technician=technician_user,
    )

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/record-balance/",
        {"amount": "1200.00", "method": "CASH"},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    payment = Payment.objects.get()
    assert payment.provider == PaymentProvider.OFFLINE
    assert payment.payment_type == PaymentType.BALANCE
    assert payment.status == PaymentRecordStatus.SUCCESS
    assert booking.balance_collected == Decimal("1200.00")
    assert booking.payment_status == PaymentStatus.PAID


@pytest.mark.django_db
def test_record_balance_rejects_overpayment(admin_client, customer, service, address, service_area, technician_user):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area),
        booking_status=BookingStatus.IN_PROGRESS,
        assigned_technician=technician_user,
    )

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/record-balance/",
        {"amount": "1200.01", "method": "UPI"},
        format="json",
    )

    assert response.status_code == 400
    assert Payment.objects.count() == 0


@pytest.mark.django_db
def test_admin_cancel_valid_transition(admin_client, customer, service, address, service_area):
    booking = create_booking(customer, service, address, create_slot(service_area))

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/cancel/", {"notes": "Customer called."}, format="json")

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.CANCELLED
    assert booking.cancelled_at is not None


@pytest.mark.django_db
def test_admin_cancel_rejects_completed(admin_client, customer, service, address, service_area, technician_user):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area),
        booking_status=BookingStatus.COMPLETED,
        assigned_technician=technician_user,
    )

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/cancel/", {}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_customer_cancel_valid_transition(customer_client, customer, service, address, service_area):
    booking = create_booking(customer, service, address, create_slot(service_area, days=2))

    response = customer_client.post(f"/api/v1/bookings/{booking.id}/cancel/", {}, format="json")

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.CANCELLED


@pytest.mark.django_db
def test_customer_cancel_policy_window(customer_client, customer, service, address, service_area, settings):
    settings.BOOKING_CUSTOMER_CANCEL_MIN_HOURS = 48
    booking = create_booking(customer, service, address, create_slot(service_area, days=1))

    response = customer_client.post(f"/api/v1/bookings/{booking.id}/cancel/", {}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_customer_reschedule_valid_transition(customer_client, customer, service, address, service_area):
    old_slot = create_slot(service_area, days=2, start_hour=10)
    new_slot = create_slot(service_area, days=3, start_hour=12)
    booking = create_booking(customer, service, address, old_slot)

    response = customer_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"slot_id": str(new_slot.id), "notes": "Move please."},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.time_slot_id == new_slot.id
    assert booking.service_date == new_slot.date


@pytest.mark.django_db
def test_customer_reschedule_rejects_pending_payment(customer_client, customer, service, address, service_area):
    booking = create_booking(
        customer,
        service,
        address,
        create_slot(service_area, days=2),
        booking_status=BookingStatus.PENDING_PAYMENT,
        payment_status=PaymentStatus.UNPAID,
    )
    new_slot = create_slot(service_area, days=3, start_hour=12)

    response = customer_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"slot_id": str(new_slot.id)},
        format="json",
    )

    assert response.status_code == 400
