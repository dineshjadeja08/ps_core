from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import CustomerSupportNote, UserRole
from apps.bookings.models import BookingStatus, PaymentStatus
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent, NotificationStatus
from apps.operations.models import Lead, LeadStatus, LeadStatusHistory
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType
from tests.factories import address_factory, booking_factory, service_area_factory, service_factory, slot_factory, user_factory


@pytest.fixture
def admin_user():
    return user_factory("+919620000001", role=UserRole.ADMIN, is_staff=True)


@pytest.fixture
def customer():
    return user_factory("+919620000002", role=UserRole.CUSTOMER)


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def booking(customer):
    service_area = service_area_factory()
    service = service_factory()
    address = address_factory(customer)
    slot = slot_factory(service_area)
    return booking_factory(customer, service, address, slot)


@pytest.mark.django_db
def test_admin_can_create_list_and_convert_lead(admin_client, admin_user, booking):
    create_response = admin_client.post(
        "/api/v1/admin/leads/",
        {
            "customer_name": "Dinesh",
            "primary_mobile": "+919620000099",
            "required_service": str(booking.service_id),
            "city": "Chennai",
            "pincode": "600001",
            "source": "PHONE",
            "status": "NEW",
        },
        format="json",
    )
    assert create_response.status_code == 201

    lead_id = create_response.json()["id"]
    assert Lead.objects.get(id=lead_id).created_by == admin_user

    list_response = admin_client.get("/api/v1/admin/leads/?search=9620000099")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    convert_response = admin_client.post(
        f"/api/v1/admin/leads/{lead_id}/convert/",
        {"booking_id": str(booking.id), "notes": "Converted after call."},
        format="json",
    )
    assert convert_response.status_code == 200
    assert convert_response.json()["status"] == LeadStatus.CONVERTED
    assert LeadStatusHistory.objects.filter(lead_id=lead_id, to_status=LeadStatus.CONVERTED).exists()


@pytest.mark.django_db
def test_admin_customer_history_and_support_note(admin_client, customer, booking):
    Lead.objects.create(customer_name="Customer", primary_mobile=customer.phone_number, status=LeadStatus.CLOSED)

    list_response = admin_client.get("/api/v1/admin/customers/?search=9620000002")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    detail_response = admin_client.get(f"/api/v1/admin/customers/{customer.id}/")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["bookings"][0]["booking_number"] == booking.booking_number
    assert detail_payload["leads"][0]["primary_mobile"] == customer.phone_number

    note_response = admin_client.post(
        f"/api/v1/admin/customers/{customer.id}/support-notes/",
        {"note": "Customer prefers morning calls."},
        format="json",
    )
    assert note_response.status_code == 201
    assert CustomerSupportNote.objects.filter(customer=customer, created_by__isnull=False).exists()


@pytest.mark.django_db
def test_admin_can_list_payments_and_create_advance_order(admin_client, booking):
    Payment.objects.create(
        booking=booking,
        provider=PaymentProvider.OFFLINE,
        amount=Decimal("1200.00"),
        payment_type=PaymentType.BALANCE,
        status=PaymentRecordStatus.SUCCESS,
    )
    list_response = admin_client.get("/api/v1/admin/payments/?search=PS-FLOW")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    pending_booking = booking_factory(
        booking.customer,
        booking.service,
        booking.address,
        booking.time_slot,
        booking_number="PS-PENDING",
        advance_paid=Decimal("0.00"),
        balance_due=Decimal("1499.00"),
        booking_status=BookingStatus.PENDING_PAYMENT,
        payment_status=PaymentStatus.UNPAID,
    )
    order_response = admin_client.post(f"/api/v1/admin/payments/booking/{pending_booking.id}/advance-order/")
    assert order_response.status_code == 201
    assert order_response.json()["booking_id"] == str(pending_booking.id)
    assert Payment.objects.filter(booking=pending_booking, payment_type=PaymentType.BOOKING_ADVANCE).exists()


@pytest.mark.django_db
def test_admin_notification_list_cancel_and_send(admin_client, customer, booking):
    queued = Notification.objects.create(
        recipient=customer,
        booking=booking,
        event=NotificationEvent.BOOKING_CONFIRMED,
        channel=NotificationChannel.IN_APP,
        title="Queued",
        message="Queued message",
    )
    failed = Notification.objects.create(
        recipient=customer,
        booking=booking,
        event=NotificationEvent.BOOKING_CONFIRMED,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.FAILED,
        title="Failed",
        message="Failed message",
    )

    list_response = admin_client.get("/api/v1/admin/notifications/?status=FAILED")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    cancel_response = admin_client.post(f"/api/v1/admin/notifications/{queued.id}/cancel/", {"reason": "Duplicate"}, format="json")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == NotificationStatus.CANCELLED

    retry_response = admin_client.post(f"/api/v1/admin/notifications/{failed.id}/retry/", {}, format="json")
    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == NotificationStatus.SENT
