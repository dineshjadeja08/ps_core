from datetime import time

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from apps.scheduling.models import TimeSlot


DEFAULT_DAILY_SLOT_WINDOWS = (
    (8, 10),
    (10, 12),
    (12, 14),
    (14, 16),
    (16, 18),
    (18, 20),
)
DEFAULT_DAILY_SLOT_CAPACITY = 20
BOOKING_CAPACITY_STATUSES = {
    "PENDING_PAYMENT",
    "CONFIRMED",
    "TECHNICIAN_ASSIGNED",
    "TECHNICIAN_EN_ROUTE",
    "IN_PROGRESS",
}


def is_slot_expired(slot, now=None):
    now = now or timezone.localtime()
    if slot.date < now.date():
        return True
    if slot.date == now.date() and slot.start_time <= now.time():
        return True
    return False


def count_reserved_bookings(slot):
    if not apps.is_installed("apps.bookings"):
        return 0

    Booking = apps.get_model("bookings", "Booking", require_ready=False)
    return Booking.objects.filter(
        time_slot=slot,
        booking_status__in=BOOKING_CAPACITY_STATUSES,
    ).count()


def get_available_capacity(slot):
    return max(slot.capacity - count_reserved_bookings(slot), 0)


def ensure_daily_slots(service_area, service_date):
    if service_date < timezone.localdate():
        return

    for start_hour, end_hour in DEFAULT_DAILY_SLOT_WINDOWS:
        TimeSlot.objects.get_or_create(
            service_area=service_area,
            date=service_date,
            start_time=time(start_hour, 0),
            end_time=time(end_hour, 0),
            defaults={"capacity": DEFAULT_DAILY_SLOT_CAPACITY, "is_active": True},
        )


def is_slot_bookable(slot):
    return (
        slot.is_active
        and slot.service_area.is_active
        and slot.capacity > 0
        and not is_slot_expired(slot)
        and get_available_capacity(slot) > 0
    )


@transaction.atomic
def lock_slot_for_reservation(slot_id):
    slot = TimeSlot.objects.select_for_update().select_related("service_area").get(id=slot_id)
    if not is_slot_bookable(slot):
        raise SlotNotAvailable("The selected slot is no longer available.")
    return slot


class SlotNotAvailable(Exception):
    pass
