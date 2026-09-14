from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent, NotificationStatus
from apps.notifications.services import send_notification
from apps.scheduling.models import TimeSlot


pytestmark = pytest.mark.django_db


@pytest.fixture
def notification(settings, monkeypatch):
    settings.NOTIFICATION_PROVIDER = "apps.notifications.providers.Msg91WhatsAppNotificationProvider"
    settings.MSG91_AUTH_KEY = "test-auth-key"
    settings.MSG91_WHATSAPP_OTP_URL = "https://api.msg91.test/whatsapp/bulk/"
    settings.MSG91_WHATSAPP_INTEGRATED_NUMBER = "911234567890"
    settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE = "namespace"
    settings.MSG91_WHATSAPP_TEMPLATE_LANGUAGE = "en"
    settings.MSG91_WHATSAPP_NOTIFICATION_TEMPLATE_NAME = "booking_update"
    settings.MSG91_WEBHOOK_SECRET = "webhook-secret"
    customer = User.objects.create_user("+919876543210", role=UserRole.CUSTOMER, is_verified=True)
    area = ServiceArea.objects.create(name="Area", city="Chennai", state="Tamil Nadu", postal_code="600001")
    category = ServiceCategory.objects.create(name="AC", slug="ac")
    service = Service.objects.create(
        category=category,
        name="AC Service",
        slug="ac-service",
        base_price=499,
        advance_amount=99,
        estimated_duration_minutes=60,
    )
    address = Address.objects.create(customer=customer, label="Home", recipient_name="Customer", phone=customer.phone_number, address_line_1="1 Road", city="Chennai", state="Tamil Nadu", postal_code="600001")
    slot = TimeSlot.objects.create(service_area=area, date=timezone.localdate() + timedelta(days=1), start_time=time(10), end_time=time(12), capacity=2)
    booking = Booking.objects.create(
        booking_number="PS-WA001", customer=customer, service=service, address=address,
        address_snapshot={}, service_date=slot.date, time_slot=slot, problem_description="Test",
        subtotal=Decimal("499.00"), total_amount=Decimal("499.00"), advance_required=Decimal("99.00"),
        balance_due=Decimal("499.00"), booking_status=BookingStatus.CONFIRMED, payment_status=PaymentStatus.PARTIALLY_PAID,
    )
    item = Notification.objects.create(
        recipient=customer, booking=booking, event=NotificationEvent.BOOKING_CONFIRMED,
        channel=NotificationChannel.WHATSAPP, title="Booking confirmed", message="PS-WA001 is confirmed.",
    )
    response = Mock(status_code=200)
    response.json.return_value = {"status": "success", "request_id": "msg-request-1"}
    post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", post)
    return item, post


def test_msg91_whatsapp_provider_sends_template_with_correlation_id(notification):
    item, post = notification
    send_notification(item)

    item.refresh_from_db()
    assert item.status == NotificationStatus.SENT
    assert item.provider == "msg91-whatsapp"
    assert item.provider_message_id == "msg-request-1"
    body = post.call_args.kwargs["json"]
    assert body["CRQID"] == str(item.id)
    assert body["payload"]["template"]["name"] == "booking_update"
    assert body["payload"]["template"]["to_and_components"][0]["to"] == ["919876543210"]


def test_msg91_delivery_callback_updates_status(notification):
    item, _ = notification
    item.provider = "msg91-whatsapp"
    item.provider_message_id = "msg-request-1"
    item.status = NotificationStatus.SENT
    item.save()

    response = APIClient().post(
        "/api/v1/notifications/webhooks/msg91/",
        {"CRQID": str(item.id), "request_id": "msg-request-1", "status": "Delivered"},
        format="json",
        HTTP_X_MSG91_WEBHOOK_SECRET="webhook-secret",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.status == NotificationStatus.DELIVERED


def test_msg91_delivery_callback_rejects_bad_secret(notification):
    item, _ = notification
    response = APIClient().post(
        "/api/v1/notifications/webhooks/msg91/",
        {"CRQID": str(item.id), "status": "Delivered"},
        format="json",
        HTTP_X_MSG91_WEBHOOK_SECRET="wrong",
    )
    assert response.status_code == 403
