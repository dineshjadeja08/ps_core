from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory
from apps.notifications.models import NotificationEvent
from apps.notifications.services import emit_notification_event
from apps.technicians.models import (
    TechnicianAssignment,
    TechnicianAvailabilityStatus,
    TechnicianProfile,
    TechnicianVerificationStatus,
)


ASSIGNABLE_STATUSES = {BookingStatus.CONFIRMED, BookingStatus.TECHNICIAN_ASSIGNED}
TECHNICIAN_BUSY_STATUSES = {
    BookingStatus.TECHNICIAN_ASSIGNED,
    BookingStatus.TECHNICIAN_EN_ROUTE,
    BookingStatus.IN_PROGRESS,
}


def slot_start_end(slot):
    start_at = timezone.make_aware(
        timezone.datetime.combine(slot.date, slot.start_time),
        timezone.get_current_timezone(),
    )
    end_at = timezone.make_aware(
        timezone.datetime.combine(slot.date, slot.end_time),
        timezone.get_current_timezone(),
    )
    return start_at, end_at


def get_technician_eligibility_errors(technician, booking):
    errors = []
    slot = booking.time_slot
    address = booking.address
    service_area = slot.service_area

    if not technician.is_active:
        errors.append("Technician is inactive.")
    if technician.background_verification_status != TechnicianVerificationStatus.VERIFIED:
        errors.append("Technician is not verified.")
    if not technician.is_available or technician.availability_status != TechnicianAvailabilityStatus.AVAILABLE:
        errors.append("Technician is not available.")
    if technician.supported_services.exists() and not technician.supported_services.filter(id=booking.service_id).exists():
        errors.append("Technician does not support this service.")
    if technician.service_areas.exists() and not technician.service_areas.filter(id=service_area.id).exists():
        errors.append("Technician does not cover this service area.")
    if address and address.postal_code and technician.pincode and technician.pincode != address.postal_code:
        errors.append("Technician pincode does not match the service address.")

    slot_start, slot_end = slot_start_end(slot)
    working_hours = technician.working_hours.filter(day_of_week=slot.date.weekday(), is_active=True)
    if working_hours.exists() and not working_hours.filter(start_time__lte=slot.start_time, end_time__gte=slot.end_time).exists():
        errors.append("Technician is not working during this slot.")
    if technician.leaves.filter(is_active=True, start_at__lt=slot_end, end_at__gt=slot_start).exists():
        errors.append("Technician is on leave during this slot.")
    if has_overlapping_booking(technician, booking):
        errors.append("Technician already has an overlapping booking.")
    return errors


def get_eligible_technicians(booking):
    technicians = (
        TechnicianProfile.objects.select_related("user")
        .prefetch_related("skills", "service_areas", "supported_services", "working_hours", "leaves")
        .filter(
            is_active=True,
            is_available=True,
            background_verification_status=TechnicianVerificationStatus.VERIFIED,
            availability_status=TechnicianAvailabilityStatus.AVAILABLE,
        )
    )
    return [technician for technician in technicians if not get_technician_eligibility_errors(technician, booking)]


def has_overlapping_booking(technician, booking):
    slot = booking.time_slot
    return (
        Booking.objects.select_related("time_slot")
        .filter(
            assigned_technician=technician.user,
            service_date=slot.date,
            booking_status__in=TECHNICIAN_BUSY_STATUSES,
            time_slot__start_time__lt=slot.end_time,
            time_slot__end_time__gt=slot.start_time,
        )
        .exclude(id=booking.id)
        .exists()
    )


@transaction.atomic
def assign_technician(*, booking_id, technician_id, assigned_by, notes="", reason=""):
    try:
        booking = Booking.objects.select_for_update().select_related("address", "service", "time_slot", "time_slot__service_area").get(id=booking_id)
    except Booking.DoesNotExist as exc:
        raise serializers.ValidationError("Booking was not found.") from exc

    if booking.booking_status not in ASSIGNABLE_STATUSES:
        raise serializers.ValidationError("Booking is not assignable.")

    try:
        technician = (
            TechnicianProfile.objects.select_for_update()
            .select_related("user")
            .prefetch_related("skills", "service_areas", "supported_services", "working_hours", "leaves")
            .get(id=technician_id)
        )
    except TechnicianProfile.DoesNotExist as exc:
        raise serializers.ValidationError("Technician was not found.") from exc

    eligibility_errors = get_technician_eligibility_errors(technician, booking)
    if eligibility_errors:
        raise serializers.ValidationError({"technician_id": eligibility_errors})

    previous_status = booking.booking_status
    previous_assignment = (
        TechnicianAssignment.objects.select_for_update()
        .filter(booking=booking, unassigned_at__isnull=True)
        .order_by("-assigned_at")
        .first()
    )
    previous_technician = previous_assignment.technician if previous_assignment else None
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
            previous_technician=previous_technician if previous_technician != technician else None,
            assigned_by=assigned_by,
            reason=reason,
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
        notes=notes or reason or "Technician assigned.",
    )
    emit_notification_event(
        event=NotificationEvent.TECHNICIAN_ASSIGNED,
        recipient=booking.customer,
        booking=booking,
        payload={"technician_id": str(technician.id)},
    )
    return assignment


@transaction.atomic
def remove_technician_assignment(*, booking_id, changed_by, notes=""):
    try:
        booking = Booking.objects.select_for_update().get(id=booking_id)
    except Booking.DoesNotExist as exc:
        raise serializers.ValidationError("Booking was not found.") from exc

    assignment = (
        TechnicianAssignment.objects.select_for_update()
        .filter(booking=booking, unassigned_at__isnull=True)
        .order_by("-assigned_at")
        .first()
    )
    if assignment is None:
        raise serializers.ValidationError("Booking does not have an active technician assignment.")

    assignment.unassigned_at = timezone.now()
    assignment.notes = "\n".join(part for part in [assignment.notes, notes] if part)
    assignment.save(update_fields=["unassigned_at", "notes", "updated_at"])

    previous_status = booking.booking_status
    booking.assigned_technician = None
    if booking.booking_status == BookingStatus.TECHNICIAN_ASSIGNED:
        booking.booking_status = BookingStatus.CONFIRMED
    booking.save(update_fields=["assigned_technician", "booking_status", "updated_at"])
    BookingStatusHistory.objects.create(
        booking=booking,
        from_status=previous_status,
        to_status=booking.booking_status,
        changed_by=changed_by,
        notes=notes or "Technician assignment removed.",
    )
    return booking
