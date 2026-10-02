from unittest.mock import Mock

import pytest

from apps.notifications.models import Notification, NotificationChannel, NotificationEvent
from apps.notifications.providers import Msg91SmsNotificationProvider
from tests.factories import user_factory


@pytest.mark.django_db
def test_msg91_sms_provider_sends_approved_flow_template(settings, monkeypatch):
    settings.MSG91_AUTH_KEY = "server-auth-key"
    settings.MSG91_SMS_TEMPLATE_ID = "fallback-template"
    settings.MSG91_SMS_TEMPLATE_IDS = {NotificationEvent.BOOKING_CONFIRMED: "booking-template"}
    customer = user_factory("+919876543210")
    notification = Notification.objects.create(
        recipient=customer,
        event=NotificationEvent.BOOKING_CONFIRMED,
        channel=NotificationChannel.SMS,
        title="Booking confirmed",
        message="Your Purple Squad booking is confirmed.",
    )
    response = Mock(status_code=200)
    response.json.return_value = {"type": "success", "request_id": "msg91-request-1"}
    post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", post)

    result = Msg91SmsNotificationProvider().send(notification)

    assert result.provider == "msg91-sms"
    assert result.provider_message_id == "msg91-request-1"
    request = post.call_args
    assert request.args[0] == "https://control.msg91.com/api/v5/flow"
    assert request.kwargs["headers"]["authkey"] == "server-auth-key"
    assert request.kwargs["json"]["template_id"] == "booking-template"
    recipient = request.kwargs["json"]["recipients"][0]
    assert recipient["mobiles"] == "919876543210"
    assert recipient["VAR1"] == str(notification.id)[:40]
    assert recipient["VAR2"] == "Booking confirmed"
    assert "VAR3" not in recipient


@pytest.mark.django_db
def test_msg91_sms_provider_uses_payload_mobile_for_manual_lead(settings, monkeypatch):
    settings.MSG91_AUTH_KEY = "server-auth-key"
    settings.MSG91_SMS_TEMPLATE_ID = "fallback-template"
    settings.MSG91_SMS_TEMPLATE_IDS = {}
    settings.MSG91_SMS_ENABLED_EVENTS = [NotificationEvent.PAYMENT_PENDING]
    notification = Notification.objects.create(
        event=NotificationEvent.PAYMENT_PENDING,
        channel=NotificationChannel.SMS,
        title="Payment link",
        message="Pay using https://example.com/pay",
        payload={"mobile": "9876543210", "amount": "299.00", "payment_link_url": "https://example.com/pay"},
    )
    response = Mock(status_code=200)
    response.json.return_value = {"type": "success", "request_id": "msg91-request-2"}
    post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", post)

    Msg91SmsNotificationProvider().send(notification)

    recipient = post.call_args.kwargs["json"]["recipients"][0]
    assert recipient["mobiles"] == "919876543210"
    assert recipient["VAR1"] == "299.00"
    assert recipient["VAR2"] == "https://example.com/pay"


@pytest.mark.django_db
def test_msg91_sms_provider_rejects_missing_configuration(settings):
    settings.MSG91_AUTH_KEY = ""
    settings.MSG91_SMS_TEMPLATE_ID = ""
    settings.MSG91_SMS_TEMPLATE_IDS = {}
    customer = user_factory("+919876543210")
    notification = Notification.objects.create(
        recipient=customer,
        event=NotificationEvent.BOOKING_CONFIRMED,
        channel=NotificationChannel.SMS,
        title="Booking confirmed",
        message="Confirmed.",
    )

    with pytest.raises(ValueError, match="not fully configured"):
        Msg91SmsNotificationProvider().send(notification)
