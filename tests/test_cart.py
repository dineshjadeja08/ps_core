from decimal import Decimal
import pytest
from rest_framework.test import APIClient
from apps.bookings.models import Booking, CartItem, PaymentStatus
from apps.catalogue.models import Service
from tests.test_bookings import customer, other_customer, authenticated_client, service_area, service, address, slot, booking_payload

pytestmark = pytest.mark.django_db

def add(client, *services):
    return client.post("/api/v1/cart/", {"service_ids": [str(item.id) for item in services]}, format="json")

def test_cart_requires_authentication():
    assert APIClient().get("/api/v1/cart/").status_code == 401

def test_cart_prices_are_server_owned_and_merge_is_idempotent(authenticated_client, service):
    assert add(authenticated_client, service).status_code == 200
    response = authenticated_client.post("/api/v1/cart/", {"service_ids": [str(service.id)], "price": 1}, format="json")
    assert response.data["count"] == 1
    assert Decimal(response.data["total"]) == service.effective_price
    service.base_price = Decimal("2000.00")
    service.save()
    assert Decimal(authenticated_client.get("/api/v1/cart/").data["total"]) == service.effective_price

def test_cart_isolated_between_customers(authenticated_client, customer, other_customer, service):
    add(authenticated_client, service)
    other = APIClient(); other.force_authenticate(other_customer)
    assert other.get("/api/v1/cart/").data["count"] == 0
    other.delete(f"/api/v1/cart/items/{service.id}/")
    assert CartItem.objects.filter(customer=customer).count() == 1

def test_inactive_service_cannot_be_added(authenticated_client, service):
    service.is_active = False; service.save()
    assert add(authenticated_client, service).status_code == 400
    assert CartItem.objects.count() == 0

def test_checkout_retry_reuses_booking(authenticated_client, service, address, slot):
    add(authenticated_client, service)
    body = {"items": [booking_payload(service, address, slot)]}
    first = authenticated_client.post("/api/v1/cart/checkout/", body, format="json")
    second = authenticated_client.post("/api/v1/cart/checkout/", body, format="json")
    assert first.status_code == second.status_code == 200
    assert first.data["bookings"][0]["id"] == second.data["bookings"][0]["id"]
    assert Booking.objects.count() == 1
    assert Decimal(first.data["cart"]["total"]) == service.effective_price

def test_checkout_batch_rolls_back_if_capacity_is_insufficient(authenticated_client, service, address, slot):
    second = Service.objects.create(category=service.category, name="Second", slug="second", base_price=499, advance_amount=99, estimated_duration_minutes=60)
    add(authenticated_client, service, second)
    slot.capacity = 1; slot.save()
    response = authenticated_client.post("/api/v1/cart/checkout/", {"items": [booking_payload(service, address, slot), booking_payload(second, address, slot)]}, format="json")
    assert response.status_code == 400
    assert Booking.objects.count() == 0
    assert not CartItem.objects.filter(booking__isnull=False).exists()

def test_checkout_batch_creates_all_and_rejects_foreign_address(authenticated_client, other_customer, service, address, slot):
    add(authenticated_client, service)
    address.customer = other_customer; address.save()
    response = authenticated_client.post("/api/v1/cart/checkout/", {"items": [booking_payload(service, address, slot)]}, format="json")
    assert response.status_code == 400
    assert not Booking.objects.exists()

def test_paid_service_removed_from_cart_without_canceling_booking(authenticated_client, service, address, slot):
    add(authenticated_client, service)
    authenticated_client.post("/api/v1/cart/checkout/", {"items": [booking_payload(service, address, slot)]}, format="json")
    booking = Booking.objects.get()
    booking.payment_status = PaymentStatus.PARTIALLY_PAID; booking.advance_paid = booking.advance_required; booking.save()
    assert authenticated_client.get("/api/v1/cart/").data["count"] == 0
    assert Booking.objects.count() == 1


def test_merge_skips_unavailable_service_and_reports_it(authenticated_client, service):
    service.is_active = False; service.save()
    response = authenticated_client.post("/api/v1/cart/", {"service_ids": [str(service.id)], "merge": True}, format="json")
    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["unavailable_service_ids"] == [str(service.id)]

def test_batch_checkout_creates_multiple_services_atomically(authenticated_client, service, address, slot):
    second = Service.objects.create(category=service.category, name="Second", slug="second", base_price=499, advance_amount=99, estimated_duration_minutes=60)
    add(authenticated_client, service, second)
    body = {"items": [booking_payload(service, address, slot), booking_payload(second, address, slot)]}
    response = authenticated_client.post("/api/v1/cart/checkout/", body, format="json")
    assert response.status_code == 200
    assert len(response.data["bookings"]) == 2
    assert Booking.objects.count() == 2
    again = authenticated_client.post("/api/v1/cart/checkout/", body, format="json")
    assert again.status_code == 200
    assert Booking.objects.count() == 2

def test_legacy_merge_keeps_own_pending_booking_and_rejects_foreign_booking(authenticated_client, service, address, slot, other_customer):
    from apps.bookings.services import create_booking
    booking = create_booking(customer=address.customer, **{key: value for key, value in booking_payload(service, address, slot).items()})
    payload = {"service_ids": [str(service.id)], "merge": True, "booking_ids": {str(service.id): str(booking.id)}}
    response = authenticated_client.post("/api/v1/cart/", payload, format="json")
    assert response.status_code == 200
    assert response.data["items"][0]["bookingId"] == str(booking.id)
    other = APIClient(); other.force_authenticate(other_customer)
    assert other.post("/api/v1/cart/", payload, format="json").status_code == 400
    assert not CartItem.objects.filter(customer=other_customer).exists()
