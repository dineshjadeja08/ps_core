from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.bookings.models import BookingStatusHistory
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType
from tests.factories import address_factory, booking_factory, service_area_factory, service_factory, slot_factory, user_factory


pytestmark = pytest.mark.django_db


@pytest.fixture
def booking():
    customer = user_factory("+919630002001", first_name="Customer")
    return booking_factory(customer, service_factory(), address_factory(customer), slot_factory(service_area_factory()))


def test_activity_endpoint_includes_scoped_events_without_sensitive_payload(booking):
    admin = user_factory("+919630002002", role=UserRole.ADMIN, is_staff=True, first_name="Operations")
    client = APIClient()
    client.force_authenticate(user=admin)
    history = BookingStatusHistory.objects.create(booking=booking, to_status="CONFIRMED", changed_by=admin, notes="Customer confirmed")
    log = AuditLog.objects.create(actor=admin, action=AuditAction.TECHNICIAN_ASSIGN, resource_type="booking", resource_id=str(booking.id), metadata={"notes": "Assigned nearby technician", "token": "do-not-expose"})
    AuditLog.objects.create(actor=admin, action=AuditAction.TECHNICIAN_ASSIGN, resource_type="booking", resource_id="another-booking", metadata={"notes": "Other customer private notes"})
    payment = Payment.objects.create(booking=booking, provider=PaymentProvider.OFFLINE, amount=Decimal("299"), payment_type=PaymentType.BOOKING_ADVANCE, status=PaymentRecordStatus.SUCCESS, provider_payload={"secret": "do-not-expose"})
    response = client.get(f"/api/v1/admin/bookings/{booking.id}/activities/")
    assert response.status_code == 200
    events = response.json()
    assert {item["id"] for item in events} == {f"booking-{booking.id}", f"status-{history.id}", f"audit-{log.id}", f"payment-{payment.id}"}
    assert next(item for item in events if item["id"] == f"status-{history.id}")["actor"] == "Operations"
    assert "do-not-expose" not in response.content.decode()
    assert "Other customer private notes" not in response.content.decode()
    assert [item["created_at"] for item in events] == sorted([item["created_at"] for item in events], reverse=True)


def test_customers_cannot_read_admin_activity(booking):
    client = APIClient()
    client.force_authenticate(user=booking.customer)
    assert client.get(f"/api/v1/admin/bookings/{booking.id}/activities/").status_code == 403


def test_missing_booking_activity_returns_404():
    client = APIClient()
    client.force_authenticate(user=user_factory("+919630002003", role=UserRole.ADMIN, is_staff=True))
    assert client.get("/api/v1/admin/bookings/00000000-0000-0000-0000-000000000000/activities/").status_code == 404


def test_operations_staff_can_read_booking_activity(booking):
    admin = user_factory("+919630002004", role=UserRole.ADMIN, is_staff=True)
    admin.groups.add(Group.objects.create(name="Operations Admin"))
    client = APIClient()
    client.force_authenticate(user=admin)
    assert client.get(f"/api/v1/admin/bookings/{booking.id}/activities/").status_code == 200
