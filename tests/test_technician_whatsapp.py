from unittest.mock import Mock

import pytest
import requests
from django.db import transaction

from apps.accounts.models import UserRole
from apps.notifications.models import Notification, NotificationChannel, NotificationStatus
from apps.notifications.providers import Msg91WhatsAppNotificationProvider
from apps.notifications.tasks import deliver_notification
from apps.technicians.services import assign_technician
from tests.factories import address_factory, booking_factory, service_area_factory, service_factory, slot_factory, technician_factory, user_factory


pytestmark = pytest.mark.django_db


@pytest.fixture
def assignment_setup(settings, monkeypatch):
    settings.MSG91_WHATSAPP_ENABLED = True
    settings.MSG91_WHATSAPP_AUTH_KEY = "test-whatsapp-key"
    settings.MSG91_WHATSAPP_INTEGRATED_NUMBER = "919876540000"
    settings.MSG91_WHATSAPP_TECHNICIAN_TEMPLATE = "technician_assignment"
    settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE = "test-namespace"
    settings.MSG91_WHATSAPP_TEMPLATE_LANGUAGE = "en"
    area = service_area_factory()
    customer = user_factory("+919876543210")
    booking = booking_factory(customer, service_factory(), address_factory(customer), slot_factory(area))
    technician = technician_factory(service_area=area)
    technician.whatsapp_notifications_enabled = True
    technician.save()
    admin = user_factory("+919876543299", role=UserRole.ADMIN, is_staff=True)
    response = Mock(status_code=200)
    response.json.return_value = {"status": "success", "request_id": "whatsapp-request-1"}
    post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", post)
    return booking, technician, admin, post


def assign(setup, callbacks):
    booking, technician, admin, _ = setup
    with callbacks(execute=True):
        assign_technician(booking_id=booking.id, technician_id=technician.id, assigned_by=admin)


def test_assignment_sends_whatsapp_to_technician_and_keeps_customer_sms(assignment_setup, django_capture_on_commit_callbacks):
    booking, technician, _, post = assignment_setup
    assign(assignment_setup, django_capture_on_commit_callbacks)
    notification = Notification.objects.get(channel=NotificationChannel.WHATSAPP)
    assert notification.recipient == technician.user
    assert notification.booking == booking
    assert notification.status == NotificationStatus.SENT
    assert notification.provider == "msg91-whatsapp"
    assert Notification.objects.filter(recipient=booking.customer, channel=NotificationChannel.SMS).exists()
    assert post.call_count == 1
    body = post.call_args.kwargs["json"]
    assert body["integrated_number"] == "919876540000"
    template = body["payload"]["template"]
    assert template["name"] == "technician_assignment"
    recipient = template["to_and_components"][0]
    assert recipient["to"] == [technician.phone.lstrip("+")]
    assert len(recipient["components"]) == 8
    assert recipient["components"]["body_2"]["value"] == booking.booking_number
    assert "12 Main Road" in recipient["components"]["body_7"]["value"]
    assert "google.com/maps" in recipient["components"]["body_8"]["value"]


@pytest.mark.parametrize("disabled", ["global", "technician"])
def test_notifications_require_enabled_setting_and_technician_opt_in(assignment_setup, settings, django_capture_on_commit_callbacks, disabled):
    booking, technician, _, post = assignment_setup
    if disabled == "global":
        settings.MSG91_WHATSAPP_ENABLED = False
    else:
        technician.whatsapp_notifications_enabled = False
        technician.save()
    assign(assignment_setup, django_capture_on_commit_callbacks)
    assert not Notification.objects.filter(channel=NotificationChannel.WHATSAPP).exists()
    assert Notification.objects.filter(recipient=booking.customer, channel=NotificationChannel.SMS).exists()
    post.assert_not_called()


def test_repeat_assignment_does_not_send_duplicate_whatsapp(assignment_setup, django_capture_on_commit_callbacks):
    assign(assignment_setup, django_capture_on_commit_callbacks)
    assign(assignment_setup, django_capture_on_commit_callbacks)
    assert Notification.objects.filter(channel=NotificationChannel.WHATSAPP).count() == 1
    assert assignment_setup[3].call_count == 1
    deliver_notification(str(Notification.objects.get(channel=NotificationChannel.WHATSAPP).id))
    assert assignment_setup[3].call_count == 1


def test_reassignment_alerts_new_technician_and_blocks_stale_retry(assignment_setup, django_capture_on_commit_callbacks):
    booking, _, admin, post = assignment_setup
    assign(assignment_setup, django_capture_on_commit_callbacks)
    old = Notification.objects.get(channel=NotificationChannel.WHATSAPP)
    next_technician = technician_factory(phone_number="+919876543301", code="TECH-NEXT", service_area=booking.time_slot.service_area)
    next_technician.whatsapp_notifications_enabled = True
    next_technician.save()
    with django_capture_on_commit_callbacks(execute=True):
        assign_technician(booking_id=booking.id, technician_id=next_technician.id, assigned_by=admin)
    assert Notification.objects.filter(channel=NotificationChannel.WHATSAPP, recipient=next_technician.user).exists()
    assert post.call_count == 2
    with pytest.raises(ValueError, match="no longer active"):
        Msg91WhatsAppNotificationProvider().send(old)
    assert post.call_count == 2


def test_whatsapp_failure_preserves_assignment_and_failed_notification(assignment_setup, django_capture_on_commit_callbacks):
    booking, technician, _, post = assignment_setup
    post.side_effect = requests.Timeout("Provider timed out")
    assign(assignment_setup, django_capture_on_commit_callbacks)
    booking.refresh_from_db()
    assert booking.assigned_technician_id == technician.user_id
    notification = Notification.objects.get(channel=NotificationChannel.WHATSAPP)
    assert notification.status == NotificationStatus.FAILED
    assert notification.send_attempts == 1
    assert "timed out" in notification.error_message
    post.side_effect = None
    deliver_notification(str(notification.id))
    notification.refresh_from_db()
    assert notification.status == NotificationStatus.SENT
    assert notification.send_attempts == 2


def test_rolled_back_assignment_does_not_send(assignment_setup, django_capture_on_commit_callbacks):
    booking, technician, admin, post = assignment_setup
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                assign_technician(booking_id=booking.id, technician_id=technician.id, assigned_by=admin)
                raise RuntimeError("Rollback")
    assert not Notification.objects.exists()
    post.assert_not_called()


def test_missing_configuration_is_recorded_without_undoing_assignment(assignment_setup, settings, django_capture_on_commit_callbacks):
    settings.MSG91_WHATSAPP_TECHNICIAN_TEMPLATE = ""
    assign(assignment_setup, django_capture_on_commit_callbacks)
    notification = Notification.objects.get(channel=NotificationChannel.WHATSAPP)
    assert notification.status == NotificationStatus.FAILED
    assert "not fully configured" in notification.error_message
    assignment_setup[3].assert_not_called()


@pytest.mark.parametrize("payload", [{"status": "error"}, {"status": "success", "hasError": True}, {}, []])
def test_provider_rejections_are_not_marked_sent(assignment_setup, django_capture_on_commit_callbacks, payload):
    post = assignment_setup[3]
    post.return_value.json.return_value = payload
    assign(assignment_setup, django_capture_on_commit_callbacks)
    assert Notification.objects.get(channel=NotificationChannel.WHATSAPP).status == NotificationStatus.FAILED
