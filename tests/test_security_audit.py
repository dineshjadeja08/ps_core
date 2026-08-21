import hmac
from datetime import time, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.audit.services import redact_mapping
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.payments.models import Payment, PaymentRecordStatus, PaymentType
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
def booking(customer, technician_user, service_area):
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
        booking_number="PS-SEC001",
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
        balance_collected=Decimal("0.00"),
        booking_status=BookingStatus.IN_PROGRESS,
        payment_status=PaymentStatus.PARTIALLY_PAID,
        assigned_technician=technician_user,
    )


@pytest.mark.django_db
def test_denied_admin_endpoint_is_audited(django_capture_on_commit_callbacks, customer_client, booking, customer):
    with django_capture_on_commit_callbacks(execute=True):
        response = customer_client.post(f"/api/v1/admin/bookings/{booking.id}/cancel/", {}, format="json")

    assert response.status_code == 403
    audit = AuditLog.objects.get(action=AuditAction.PERMISSION_DENIED)
    assert audit.actor == customer
    assert audit.resource_type == "admin_endpoint"
    assert audit.metadata["path"].startswith("/api/v1/admin/bookings/")


@pytest.mark.django_db
def test_admin_record_balance_is_audited(django_capture_on_commit_callbacks, admin_client, booking, admin_user):
    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            f"/api/v1/admin/bookings/{booking.id}/record-balance/",
            {"amount": "1200.00", "method": "CASH", "notes": "Collected onsite."},
            format="json",
            HTTP_USER_AGENT="pytest-agent",
        )

    assert response.status_code == 200
    audit = AuditLog.objects.get(action=AuditAction.ADMIN_RECORD_BALANCE)
    assert audit.actor == admin_user
    assert audit.resource_id == str(booking.id)
    assert audit.user_agent == "pytest-agent"
    assert audit.metadata["amount"] == "1200.00"


@pytest.mark.django_db
def test_webhook_missing_signature_is_rejected_and_audited(django_capture_on_commit_callbacks):
    client = APIClient()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            "/api/v1/payments/webhooks/razorpay/",
            data=b"{}",
            content_type="application/json",
        )

    assert response.status_code == 400
    audit = AuditLog.objects.get(action=AuditAction.PAYMENT_WEBHOOK_REJECTED)
    assert audit.metadata["reason"] == "missing_signature"


@pytest.mark.django_db
def test_webhook_invalid_json_is_rejected_safely(django_capture_on_commit_callbacks, settings, booking):
    payment = Payment.objects.create(
        booking=booking,
        provider_order_id="order_bad_json",
        amount=Decimal("299.00"),
        payment_type=PaymentType.BOOKING_ADVANCE,
        status=PaymentRecordStatus.CREATED,
    )
    body = b"{not-json"
    signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, sha256).hexdigest()
    client = APIClient()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            "/api/v1/payments/webhooks/razorpay/",
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

    assert response.status_code == 400
    assert Payment.objects.get(id=payment.id).status == PaymentRecordStatus.CREATED
    assert AuditLog.objects.filter(action=AuditAction.PAYMENT_WEBHOOK_RECEIVED).exists()
    assert AuditLog.objects.filter(action=AuditAction.PAYMENT_WEBHOOK_REJECTED).exists()


def test_sensitive_audit_metadata_is_redacted():
    redacted = redact_mapping(
        {
            "razorpay_signature": "sig_123",
            "nested": {"token": "secret-token", "safe": "value"},
            "amount": Decimal("1200.00"),
        }
    )

    assert redacted["razorpay_signature"] == "***"
    assert redacted["nested"]["token"] == "***"
    assert redacted["nested"]["safe"] == "value"
    assert redacted["amount"] == "1200.00"
