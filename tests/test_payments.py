import hmac
import json
from datetime import time, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
from unittest.mock import patch
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.notifications.models import Notification, NotificationEvent
from apps.payments.models import Invoice, Payment, PaymentRecordStatus, PaymentType, PaymentWebhookEvent, WebhookProcessingStatus
from apps.payments.services import make_payment_signature
from apps.payments.tasks import reconcile_pending_refunds
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
def test_paid_customer_can_download_gst_invoice(authenticated_client, booking):
    booking.payment_status = PaymentStatus.PAID
    booking.save(update_fields=["payment_status", "updated_at"])

    response = authenticated_client.get(f"/api/v1/bookings/{booking.id}/invoice/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    invoice = Invoice.objects.get(booking=booking)
    assert invoice.invoice_number.startswith("PS/")
    assert invoice.total_amount == booking.total_amount


@pytest.mark.django_db
def test_unpaid_customer_cannot_download_invoice(authenticated_client, booking):
    response = authenticated_client.get(f"/api/v1/bookings/{booking.id}/invoice/")

    assert response.status_code == 400
    assert not Invoice.objects.filter(booking=booking).exists()


@pytest.mark.django_db
@patch("apps.payments.tasks.reconcile_refund_task.delay")
def test_pending_refunds_are_queued_for_reconciliation(delay, booking):
    refund = Payment.objects.create(
        booking=booking,
        amount=Decimal("100.00"),
        payment_type=PaymentType.REFUND,
        status=PaymentRecordStatus.PENDING,
        provider_refund_id="rfnd_pending_001",
    )

    queued = reconcile_pending_refunds.run()

    assert queued == 1
    delay.assert_called_once_with(str(refund.id))


@pytest.mark.django_db
def test_order_creation_is_idempotent_and_keeps_one_active_advance(authenticated_client, booking):
    first = authenticated_client.post(
        f"/api/v1/bookings/{booking.id}/payments/order/",
        HTTP_IDEMPOTENCY_KEY="payment-attempt-0001",
    )
    second = authenticated_client.post(
        f"/api/v1/bookings/{booking.id}/payments/order/",
        HTTP_IDEMPOTENCY_KEY="payment-attempt-0002",
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["payment_id"] == second.json()["payment_id"]
    assert Payment.objects.count() == 1
    assert Payment.objects.get().idempotency_key == "payment-attempt-0001"


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


def webhook_body(event, entity_name, entity):
    return json.dumps(
        {"event": event, "payload": {entity_name: {"entity": entity}}},
        separators=(",", ":"),
    ).encode("utf-8")


def post_webhook(body, settings):
    signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, sha256).hexdigest()
    return APIClient().post(
        "/api/v1/payments/webhooks/razorpay/",
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
    )


@pytest.mark.django_db
def test_payment_failed_webhook_allows_new_order_and_notifies(
    authenticated_client,
    booking,
    settings,
    django_capture_on_commit_callbacks,
):
    order = authenticated_client.post(
        f"/api/v1/bookings/{booking.id}/payments/order/",
        HTTP_IDEMPOTENCY_KEY="payment-attempt-failed",
    ).json()
    body = webhook_body(
        "payment.failed",
        "payment",
        {"id": "pay_failed_webhook", "order_id": order["provider_order_id"], "amount": 29900},
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = post_webhook(body, settings)

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.PAYMENT_FAILED
    assert booking.payment_status == PaymentStatus.FAILED
    assert Notification.objects.filter(event=NotificationEvent.PAYMENT_FAILED, booking=booking).exists()

    retry = authenticated_client.post(
        f"/api/v1/bookings/{booking.id}/payments/order/",
        HTTP_IDEMPOTENCY_KEY="payment-attempt-retry",
    )
    assert retry.status_code == 201
    assert Payment.objects.filter(payment_type=PaymentType.BOOKING_ADVANCE).count() == 2


@pytest.mark.django_db
def test_failed_webhook_processing_is_recorded_and_can_be_retried(settings):
    body = webhook_body("payment.captured", "payment", {"id": "pay_incomplete"})

    first = post_webhook(body, settings)
    second = post_webhook(body, settings)

    assert first.status_code == second.status_code == 400
    record = PaymentWebhookEvent.objects.get()
    assert record.status == WebhookProcessingStatus.FAILED
    assert record.attempts == 2
    assert record.last_error == "ValidationError"


@pytest.mark.django_db
def test_admin_can_create_idempotent_refund_and_booking_is_reconciled(
    authenticated_client,
    booking,
    settings,
    django_capture_on_commit_callbacks,
):
    order = authenticated_client.post(
        f"/api/v1/bookings/{booking.id}/payments/order/",
        HTTP_IDEMPOTENCY_KEY="payment-before-refund",
    ).json()
    provider_payment_id = "pay_for_refund"
    signature = make_payment_signature(order["provider_order_id"], provider_payment_id)
    authenticated_client.post(
        "/api/v1/payments/verify/",
        {
            "razorpay_order_id": order["provider_order_id"],
            "razorpay_payment_id": provider_payment_id,
            "razorpay_signature": signature,
        },
        format="json",
    )
    source = Payment.objects.get(payment_type=PaymentType.BOOKING_ADVANCE)
    admin = User.objects.create_user(
        "+919999999999",
        role=UserRole.ADMIN,
        is_staff=True,
        is_verified=True,
    )
    client = APIClient()
    client.force_authenticate(admin)

    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(
            f"/api/v1/admin/payments/{source.id}/refund/",
            {"amount": "299.00", "reason": "Customer cancellation"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="refund-request-0001",
        )
        second = client.post(
            f"/api/v1/admin/payments/{source.id}/refund/",
            {"amount": "299.00", "reason": "Customer cancellation"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="refund-request-0001",
        )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert Payment.objects.filter(payment_type=PaymentType.REFUND).count() == 1
    refund = Payment.objects.get(payment_type=PaymentType.REFUND)
    assert refund.parent_payment == source
    assert refund.status == PaymentRecordStatus.SUCCESS
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.REFUNDED
    assert booking.payment_status == PaymentStatus.REFUNDED
    assert Notification.objects.filter(event=NotificationEvent.REFUND_INITIATED, booking=booking).exists()
    assert Notification.objects.filter(event=NotificationEvent.REFUND_COMPLETED, booking=booking).exists()
