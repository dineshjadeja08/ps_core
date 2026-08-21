from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.bookings.services import cancel_booking, complete_booking
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent, NotificationStatus
from apps.notifications.services import emit_notification_event
from apps.reviews.models import Review
from apps.scheduling.models import TimeSlot
from apps.technicians.models import TechnicianProfile, TechnicianSkill
from apps.technicians.services import assign_technician


class FailingNotificationProvider:
    provider_name = "failing-test"

    def send(self, notification):
        raise RuntimeError("provider unavailable")


@pytest.fixture
def customer():
    return User.objects.create_user("+919876543210", role=UserRole.CUSTOMER, is_verified=True)


@pytest.fixture
def other_customer():
    return User.objects.create_user("+919876543211", role=UserRole.CUSTOMER, is_verified=True)


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
def other_customer_client(other_customer):
    client = APIClient()
    client.force_authenticate(user=other_customer)
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
def service():
    category = ServiceCategory.objects.create(name="AC Service", slug="ac-service")
    return Service.objects.create(
        category=category,
        name="AC General Service",
        slug="ac-general-service",
        base_price=Decimal("1499.00"),
        advance_amount=Decimal("299.00"),
        estimated_duration_minutes=90,
    )


@pytest.fixture
def address(customer):
    return Address.objects.create(
        customer=customer,
        label="Home",
        recipient_name="Dinesh",
        phone="+919876543210",
        address_line_1="12 Main Road",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )


@pytest.fixture
def slot(service_area):
    return TimeSlot.objects.create(
        service_area=service_area,
        date=timezone.localdate() + timedelta(days=2),
        start_time=time(10, 0),
        end_time=time(12, 0),
        capacity=2,
    )


def create_booking(customer, service, address, slot, **overrides):
    data = {
        "booking_number": f"PS-REV{Booking.objects.count() + 1:03d}",
        "customer": customer,
        "service": service,
        "address": address,
        "address_snapshot": {"postal_code": address.postal_code},
        "service_date": slot.date,
        "time_slot": slot,
        "problem_description": "AC is not cooling.",
        "subtotal": Decimal("1499.00"),
        "total_amount": Decimal("1499.00"),
        "advance_required": Decimal("299.00"),
        "advance_paid": Decimal("299.00"),
        "balance_due": Decimal("1200.00"),
        "balance_collected": Decimal("1200.00"),
        "booking_status": BookingStatus.COMPLETED,
        "payment_status": PaymentStatus.PAID,
    }
    data.update(overrides)
    return Booking.objects.create(**data)


def create_technician(service_area):
    user = User.objects.create_user("+919876543301", role=UserRole.TECHNICIAN, is_verified=True)
    skill = TechnicianSkill.objects.create(name="AC repair")
    profile = TechnicianProfile.objects.create(
        user=user,
        employee_code="TECH-REV",
        display_name="Technician Rev",
        phone=user.phone_number,
        is_active=True,
        is_available=True,
    )
    profile.skills.add(skill)
    profile.service_areas.add(service_area)
    return profile


@pytest.mark.django_db
def test_completed_booking_can_be_reviewed(customer_client, customer, service, address, slot, technician_user):
    booking = create_booking(customer, service, address, slot, assigned_technician=technician_user)

    response = customer_client.post(
        f"/api/v1/bookings/{booking.id}/review/",
        {"rating": 5, "comment": "Clean work and on time."},
        format="json",
    )

    assert response.status_code == 201
    review = Review.objects.get()
    assert review.booking == booking
    assert review.customer == customer
    assert review.technician == technician_user
    assert review.rating == 5


@pytest.mark.django_db
def test_non_completed_booking_cannot_be_reviewed(customer_client, customer, service, address, slot):
    booking = create_booking(customer, service, address, slot, booking_status=BookingStatus.IN_PROGRESS)

    response = customer_client.post(
        f"/api/v1/bookings/{booking.id}/review/",
        {"rating": 4, "comment": "Still in progress."},
        format="json",
    )

    assert response.status_code == 400
    assert Review.objects.count() == 0


@pytest.mark.django_db
def test_one_review_per_booking(customer_client, customer, service, address, slot):
    booking = create_booking(customer, service, address, slot)

    first = customer_client.post(
        f"/api/v1/bookings/{booking.id}/review/",
        {"rating": 5, "comment": "Great."},
        format="json",
    )
    second = customer_client.post(
        f"/api/v1/bookings/{booking.id}/review/",
        {"rating": 4, "comment": "Trying again."},
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert Review.objects.count() == 1


@pytest.mark.django_db
def test_customer_cannot_review_someone_else_booking(other_customer_client, customer, service, address, slot):
    booking = create_booking(customer, service, address, slot)

    response = other_customer_client.post(
        f"/api/v1/bookings/{booking.id}/review/",
        {"rating": 5, "comment": "Not mine."},
        format="json",
    )

    assert response.status_code == 400
    assert Review.objects.count() == 0


@pytest.mark.django_db
def test_service_reviews_list_only_visible(customer_client, customer, service, address, slot):
    visible_booking = create_booking(customer, service, address, slot)
    hidden_booking = create_booking(customer, service, address, slot, booking_number="PS-REVHID")
    Review.objects.create(booking=visible_booking, customer=customer, rating=5, comment="Visible", is_visible=True)
    Review.objects.create(booking=hidden_booking, customer=customer, rating=1, comment="Hidden", is_visible=False)

    response = customer_client.get(f"/api/v1/services/{service.id}/reviews/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["comment"] == "Visible"


@pytest.mark.django_db
def test_emit_notification_event_sends_after_commit(django_capture_on_commit_callbacks, customer, service, address, slot):
    booking = create_booking(customer, service, address, slot)

    with django_capture_on_commit_callbacks(execute=True):
        emit_notification_event(
            event=NotificationEvent.BOOKING_CANCELLED,
            recipient=customer,
            booking=booking,
            channels=(NotificationChannel.PUSH,),
        )

    notification = Notification.objects.get()
    assert notification.event == NotificationEvent.BOOKING_CANCELLED
    assert notification.status == NotificationStatus.SENT
    assert notification.provider == "local"


@pytest.mark.django_db
def test_notification_provider_failure_is_recorded(settings, customer, service, address, slot):
    settings.NOTIFICATION_PROVIDER = "tests.test_reviews_notifications.FailingNotificationProvider"
    booking = create_booking(customer, service, address, slot)

    notification = Notification.objects.create(
        recipient=customer,
        booking=booking,
        event=NotificationEvent.SERVICE_COMPLETED,
        channel=NotificationChannel.PUSH,
        title="Service completed",
        message="Done.",
    )
    from apps.notifications.services import send_notification

    send_notification(notification)

    notification.refresh_from_db()
    assert notification.status == NotificationStatus.FAILED
    assert notification.provider == "failing-test"
    assert "provider unavailable" in notification.error_message


@pytest.mark.django_db
def test_assignment_emits_notification(django_capture_on_commit_callbacks, customer, service, address, slot, admin_user, service_area):
    booking = create_booking(
        customer,
        service,
        address,
        slot,
        booking_status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.PARTIALLY_PAID,
        balance_collected=Decimal("0.00"),
    )
    technician = create_technician(service_area)

    with django_capture_on_commit_callbacks(execute=True):
        assign_technician(booking_id=booking.id, technician_id=technician.id, assigned_by=admin_user)

    assert Notification.objects.filter(event=NotificationEvent.TECHNICIAN_ASSIGNED, booking=booking).exists()


@pytest.mark.django_db
def test_cancel_and_complete_emit_notifications(
    django_capture_on_commit_callbacks,
    customer,
    service,
    address,
    slot,
    admin_user,
    technician_user,
):
    cancellable = create_booking(customer, service, address, slot, booking_status=BookingStatus.CONFIRMED)
    completable = create_booking(
        customer,
        service,
        address,
        slot,
        booking_number="PS-REVDON",
        booking_status=BookingStatus.IN_PROGRESS,
        assigned_technician=technician_user,
    )

    with django_capture_on_commit_callbacks(execute=True):
        cancel_booking(booking_id=cancellable.id, changed_by=admin_user)
        complete_booking(booking_id=completable.id, changed_by=admin_user)

    assert Notification.objects.filter(event=NotificationEvent.BOOKING_CANCELLED, booking=cancellable).exists()
    assert Notification.objects.filter(event=NotificationEvent.SERVICE_COMPLETED, booking=completable).exists()


@pytest.mark.django_db
def test_status_history_still_written_when_notifications_run(
    django_capture_on_commit_callbacks,
    customer,
    service,
    address,
    slot,
    admin_user,
):
    booking = create_booking(customer, service, address, slot, booking_status=BookingStatus.CONFIRMED)

    with django_capture_on_commit_callbacks(execute=True):
        cancel_booking(booking_id=booking.id, changed_by=admin_user)

    assert BookingStatusHistory.objects.filter(
        booking=booking,
        to_status=BookingStatus.CANCELLED,
    ).exists()
