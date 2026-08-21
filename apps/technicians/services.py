from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory
from apps.notifications.models import NotificationEvent
from apps.notifications.services import emit_notification_event
from apps.technicians.models import TechnicianAssignment, TechnicianProfile


ASSIGNABLE_STATUSES = {BookingStatus.CONFIRMED, BookingStatus.TECHNICIAN_ASSIGNED}


@transaction.atomic
def assign_technician(*, booking_id, technician_id, assigned_by, notes=""):
    try:
        booking = Booking.objects.select_for_update().get(id=booking_id)
    except Booking.DoesNotExist as exc:
        raise serializers.ValidationError("Booking was not found.") from exc

    if booking.booking_status not in ASSIGNABLE_STATUSES:
        raise serializers.ValidationError("Booking is not assignable.")

    try:
        technician = TechnicianProfile.objects.select_related("user").get(id=technician_id, is_active=True)
    except TechnicianProfile.DoesNotExist as exc:
        raise serializers.ValidationError("Technician is not active.") from exc

    previous_status = booking.booking_status
    previous_assignment = (
        TechnicianAssignment.objects.select_for_update()
        .filter(booking=booking, unassigned_at__isnull=True)
        .order_by("-assigned_at")
        .first()
    )
    if previous_assignment and previous_assignment.technician_id != technician.id:
        previous_assignment.unassigned_at = timezone.now()
        previous_assignment.save(update_fields=["unassigned_at", "updated_at"])

    if previous_assignment and previous_assignment.technician_id == technician.id:
        assignment = previous_assignment
        if notes and assignment.notes != notes:
            assignment.notes = notes
            assignment.save(update_fields=["notes", "updated_at"])
    else:
        assignment = TechnicianAssignment.objects.create(
            booking=booking,
            technician=technician,
            assigned_by=assigned_by,
            notes=notes,
        )

    booking.assigned_technician = technician.user
    booking.booking_status = BookingStatus.TECHNICIAN_ASSIGNED
    booking.save(update_fields=["assigned_technician", "booking_status", "updated_at"])

    BookingStatusHistory.objects.create(
        booking=booking,
        from_status=previous_status,
        to_status=BookingStatus.TECHNICIAN_ASSIGNED,
        changed_by=assigned_by,
        notes=notes or "Technician assigned.",
    )
    emit_notification_event(
        event=NotificationEvent.TECHNICIAN_ASSIGNED,
        recipient=booking.customer,
        booking=booking,
        payload={"technician_id": str(technician.id)},
    )
    return assignment
