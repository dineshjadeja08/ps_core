from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.scheduling.models import TimeSlot


@pytest.fixture
def customer():
    return User.objects.create_user("+919876543210", role=UserRole.CUSTOMER, is_verified=True)


@pytest.fixture
def other_customer():
    return User.objects.create_user("+919876543211", role=UserRole.CUSTOMER, is_verified=True)


@pytest.fixture
def authenticated_client(customer):
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
    return create_address(customer)


@pytest.fixture
def slot(service_area):
    return TimeSlot.objects.create(
        service_area=service_area,
        date=timezone.localdate() + timedelta(days=1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        capacity=2,
    )


def create_address(customer, **overrides):
    data = {
        "label": "Home",
        "recipient_name": "Dinesh",
        "phone": "+919876543210",
        "address_line_1": "12 Main Road",
        "address_line_2": "",
        "landmark": "Near bus stand",
        "locality": "Central",
        "city": "Tirupattur",
        "state": "Tamil Nadu",
        "postal_code": "635601",
        "country": "India",
        "latitude": Decimal("12.490000"),
        "longitude": Decimal("78.570000"),
        "is_default": True,
    }
    data.update(overrides)
    return Address.objects.create(customer=customer, **data)


def booking_payload(service, address, slot, **overrides):
    payload = {
        "service_id": str(service.id),
        "address_id": str(address.id),
        "slot_id": str(slot.id),
        "problem_description": "AC is not cooling properly.",
        "customer_notes": "Please call before arriving.",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_booking_creation(authenticated_client, service, address, slot):
    response = authenticated_client.post(
        "/api/v1/bookings/",
        booking_payload(service, address, slot),
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["booking_number"].startswith("PS-")
    assert payload["booking_status"] == BookingStatus.PENDING_PAYMENT
    assert payload["payment_status"] == PaymentStatus.UNPAID
    assert payload["total_amount"] == "1499.00"
    assert payload["advance_required"] == "299.00"
    assert Booking.objects.count() == 1
    assert BookingStatusHistory.objects.count() == 1


@pytest.mark.django_db
def test_address_ownership(authenticated_client, service, other_customer, slot):
    other_address = create_address(other_customer)

    response = authenticated_client.post(
        "/api/v1/bookings/",
        booking_payload(service, other_address, slot),
        format="json",
    )

    assert response.status_code == 400
    assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_inactive_service(authenticated_client, service, address, slot):
    service.is_active = False
    service.save()

    response = authenticated_client.post(
        "/api/v1/bookings/",
        booking_payload(service, address, slot),
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_full_slot(authenticated_client, service, address, slot, other_customer):
    slot.capacity = 1
    slot.save()
    Booking.objects.create(
        booking_number="PS-TAKEN1",
        customer=other_customer,
        service=service,
        address=create_address(other_customer),
        address_snapshot={},
        service_date=slot.date,
        time_slot=slot,
        problem_description="Existing booking.",
        subtotal=Decimal("1499.00"),
        total_amount=Decimal("1499.00"),
        advance_required=Decimal("299.00"),
        balance_due=Decimal("1499.00"),
        booking_status=BookingStatus.PENDING_PAYMENT,
        payment_status=PaymentStatus.UNPAID,
    )

    response = authenticated_client.post(
        "/api/v1/bookings/",
        booking_payload(service, address, slot),
        format="json",
    )

    assert response.status_code == 400
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_pricing_snapshot(authenticated_client, service, address, slot):
    response = authenticated_client.post(
        "/api/v1/bookings/",
        booking_payload(service, address, slot),
        format="json",
    )
    booking = Booking.objects.get(id=response.json()["id"])

    service.base_price = Decimal("9999.00")
    service.advance_amount = Decimal("999.00")
    service.save()
    booking.refresh_from_db()

    assert booking.subtotal == Decimal("1499.00")
    assert booking.advance_required == Decimal("299.00")


@pytest.mark.django_db
def test_address_snapshot(authenticated_client, service, address, slot):
    response = authenticated_client.post(
        "/api/v1/bookings/",
        booking_payload(service, address, slot),
        format="json",
    )
    booking = Booking.objects.get(id=response.json()["id"])

    address.address_line_1 = "Changed address"
    address.save()
    booking.refresh_from_db()

    assert booking.address_snapshot["address_line_1"] == "12 Main Road"
    assert booking.address_snapshot["postal_code"] == "635601"


@pytest.mark.django_db
def test_customer_isolation(authenticated_client, service, address, slot, other_customer):
    create_response = authenticated_client.post(
        "/api/v1/bookings/",
        booking_payload(service, address, slot),
        format="json",
    )
    other_client = APIClient()
    other_client.force_authenticate(user=other_customer)

    detail = other_client.get(f"/api/v1/bookings/{create_response.json()['id']}/")
    listing = other_client.get("/api/v1/bookings/")

    assert detail.status_code == 404
    assert listing.status_code == 200
    assert listing.json()["count"] == 0
