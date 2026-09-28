from unittest.mock import Mock

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.notifications.fcm import send
from apps.notifications.models import DeviceToken, Notification, NotificationChannel, NotificationEvent


@pytest.mark.django_db
def test_register_device_upserts_token_for_authenticated_user():
    first = User.objects.create_user(phone_number="+919876543210")
    second = User.objects.create_user(phone_number="+919876543211")
    client = APIClient()
    client.force_authenticate(first)
    response = client.post("/api/v1/devices/register/", {"token": "fcm-token", "platform": "WEB"}, format="json")
    assert response.status_code == 200

    client.force_authenticate(second)
    response = client.post("/api/v1/devices/register/", {"token": "fcm-token", "platform": "ANDROID"}, format="json")
    assert response.status_code == 200
    device = DeviceToken.objects.get(token="fcm-token")
    assert device.user == second
    assert device.platform == "ANDROID"
    assert device.is_active is True


@pytest.mark.django_db
def test_fcm_send_routes_booking_notification(monkeypatch):
    user = User.objects.create_user(phone_number="+919876543210")
    DeviceToken.objects.create(user=user, token="fcm-token")
    notification = Notification.objects.create(
        recipient=user,
        event=NotificationEvent.BOOKING_CONFIRMED,
        channel=NotificationChannel.PUSH,
        title="Booking confirmed",
        message="Your booking is confirmed.",
    )
    firebase_send = Mock(return_value="projects/demo/messages/message-1")
    monkeypatch.setattr("apps.notifications.fcm.get_firebase_app", lambda: object())
    monkeypatch.setattr("apps.notifications.fcm.messaging.send", firebase_send)

    result = send(notification)

    assert result.provider == "firebase-fcm"
    assert result.provider_message_id == "projects/demo/messages/message-1"
    message = firebase_send.call_args.args[0]
    assert message.token == "fcm-token"
    assert message.data["event"] == NotificationEvent.BOOKING_CONFIRMED
