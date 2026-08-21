import hmac
import json
from datetime import time, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.payments.models import Payment, PaymentRecordStatus
from apps.payments.services import make_payment_signature
from apps.scheduling.models import TimeSlot


@pytest.fixture
def customer():
    return User.objects.create_user("+919876543210", role=UserRole.CUSTOMER, is_verified=True)


@pytest.fixture
def authenticated_client(customer):
    client = APIClient()
    client.force_authenticate(user=customer)
    return client


@pytest.fixture
def booking(customer):
    service_area = ServiceArea.objects.create(
        name="Tirupattur Central",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )
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
    booking = Booking.objects.create(
        booking_number="PS-PAY001",
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
        balance_due=Decimal("1499.00"),
        booking_status=BookingStatus.PENDING_PAYMENT,
        payment_status=PaymentStatus.UNPAID,
    )
    BookingStatusHistory.objects.create(booking=booking, to_status=BookingStatus.PENDING_PAYMENT)
    return booking


@pytest.mark.django_db
def test_order_creation(authenticated_client, booking):
    response = authenticated_client.post(f"/api/v1/bookings/{booking.id}/payments/order/")

    assert response.status_code == 201
    payload = response.json()
    assert payload["booking_id"] == str(booking.id)
    assert payload["amount"] == "299.00"
    assert payload["amount_paise"] == 29900
    assert payload["provider_order_id"].startswith("order_")
    assert Payment.objects.count() == 1


@pytest.mark.django_db
def test_successful_verification(authenticated_client, booking):
    order = authenticated_client.post(f"/api/v1/bookings/{booking.id}/payments/order/").json()
    payment_id = "pay_success_001"
    signature = make_payment_signature(order["provider_order_id"], payment_id)

    response = authenticated_client.post(
        "/api/v1/payments/verify/",
        {
            "razorpay_order_id": order["provider_order_id"],
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    payment = Payment.objects.get()
    assert payment.status == PaymentRecordStatus.SUCCESS
    assert payment.signature_verified is True
    assert booking.booking_status == BookingStatus.CONFIRMED
    assert booking.payment_status == PaymentStatus.PARTIALLY_PAID
    assert booking.advance_paid == Decimal("299.00")
    assert booking.balance_due == Decimal("1200.00")


@pytest.mark.django_db
def test_invalid_signature(authenticated_client, booking):
    order = authenticated_client.post(f"/api/v1/bookings/{booking.id}/payments/order/").json()

    response = authenticated_client.post(
        "/api/v1/payments/verify/",
        {
            "razorpay_order_id": order["provider_order_id"],
            "razorpay_payment_id": "pay_bad",
            "razorpay_signature": "bad-signature",
        },
        format="json",
    )

    assert response.status_code == 400
    assert Payment.objects.get().status == PaymentRecordStatus.FAILED


@pytest.mark.django_db
def test_duplicate_verification(authenticated_client, booking):
    order = authenticated_client.post(f"/api/v1/bookings/{booking.id}/payments/order/").json()
    payment_id = "pay_duplicate"
    signature = make_payment_signature(order["provider_order_id"], payment_id)
    payload = {
        "razorpay_order_id": order["provider_order_id"],
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature,
    }

    first = authenticated_client.post("/api/v1/payments/verify/", payload, format="json")
    second = authenticated_client.post("/api/v1/payments/verify/", payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert BookingStatusHistory.objects.filter(to_status=BookingStatus.CONFIRMED).count() == 1


@pytest.mark.django_db
def test_duplicate_webhook(authenticated_client, booking, settings):
    order = authenticated_client.post(f"/api/v1/bookings/{booking.id}/payments/order/").json()
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook",
                        "order_id": order["provider_order_id"],
                        "amount": 29900,
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, sha256).hexdigest()
    client = APIClient()

    first = client.post(
        "/api/v1/payments/webhooks/razorpay/",
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
    )
    second = client.post(
        "/api/v1/payments/webhooks/razorpay/",
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert Payment.objects.get().status == PaymentRecordStatus.SUCCESS
    assert BookingStatusHistory.objects.filter(to_status=BookingStatus.CONFIRMED).count() == 1


@pytest.mark.django_db
def test_wrong_amount(authenticated_client, booking):
    order = authenticated_client.post(f"/api/v1/bookings/{booking.id}/payments/order/").json()
    payment = Payment.objects.get(provider_order_id=order["provider_order_id"])
    payment.amount = Decimal("1.00")
    payment.save()

    response = authenticated_client.post(
        "/api/v1/payments/verify/",
        {
            "razorpay_order_id": order["provider_order_id"],
            "razorpay_payment_id": "pay_wrong_amount",
            "razorpay_signature": make_payment_signature(order["provider_order_id"], "pay_wrong_amount"),
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_unknown_order(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/payments/verify/",
        {
            "razorpay_order_id": "order_missing",
            "razorpay_payment_id": "pay_missing",
            "razorpay_signature": "signature",
        },
        format="json",
    )

    assert response.status_code == 404
