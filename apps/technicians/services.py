from django.db import transaction
from decimal import Decimal

from django.db.models import Avg, Count, Prefetch, Sum
from django.utils import timezone
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory
from apps.notifications.models import NotificationChannel, NotificationEvent
from apps.notifications.services import emit_notification_event
from apps.reviews.models import Review
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

    if booking.assigned_technician_id != technician.user_id:
        # A new technician has to accept the job themselves.
        booking.accepted_at = None
        booking.arrived_at = None
    booking.assigned_technician = technician.user
    booking.booking_status = BookingStatus.TECHNICIAN_ASSIGNED
    booking.save(update_fields=["assigned_technician", "booking_status", "accepted_at", "arrived_at", "updated_at"])

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
    emit_notification_event(
        event=NotificationEvent.JOB_ASSIGNED,
        recipient=technician.user,
        booking=booking,
        channels=(NotificationChannel.PUSH,),
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


COMPLETED_STATUSES = {BookingStatus.COMPLETED, BookingStatus.CLOSED}
CANCELLED_STATUSES = {BookingStatus.CANCELLED, BookingStatus.REFUND_PENDING, BookingStatus.REFUNDED}


def _month_start(day, months_back=0):
    month_index = day.year * 12 + day.month - 1 - months_back
    return day.replace(year=month_index // 12, month=month_index % 12 + 1, day=1)


def get_technician_performance(*, user, period="overall"):
    """Job completion, revenue and rating figures for one technician, plus a 3-month trend.

    ``period`` is "overall" or a calendar month as "YYYY-MM" (matched on service date).
    """
    bookings = Booking.objects.filter(assigned_technician=user)
    reviews = Review.objects.filter(technician=user, is_visible=True)
    if period != "overall":
        try:
            start = timezone.datetime.strptime(period, "%Y-%m").date()
        except ValueError as exc:
            raise serializers.ValidationError({"period": "Use 'overall' or YYYY-MM."}) from exc
        end = _month_start(start, -1)
        bookings = bookings.filter(service_date__gte=start, service_date__lt=end)
        reviews = reviews.filter(booking__service_date__gte=start, booking__service_date__lt=end)

    statuses = list(bookings.values_list("booking_status", flat=True))
    total = len(statuses)
    completed = sum(1 for status in statuses if status in COMPLETED_STATUSES)
    cancelled = sum(1 for status in statuses if status in CANCELLED_STATUSES)
    gross_revenue = bookings.filter(booking_status__in=COMPLETED_STATUSES).aggregate(total=Sum("total_amount"))["total"]
    rating = reviews.aggregate(average=Avg("rating"), count=Count("id"))
    completion_rate = round(completed * 100 / total) if total else 0

    today = timezone.localdate()
    trend = []
    for months_back in (2, 1, 0):
        start = _month_start(today, months_back)
        end = _month_start(today, months_back - 1)
        month_jobs = Booking.objects.filter(
            assigned_technician=user,
            booking_status__in=COMPLETED_STATUSES,
            service_date__gte=start,
            service_date__lt=end,
        )
        month_rating = Review.objects.filter(
            technician=user, is_visible=True, booking__service_date__gte=start, booking__service_date__lt=end
        ).aggregate(average=Avg("rating"))["average"]
        trend.append(
            {
                "month": start.strftime("%b"),
                "jobs": month_jobs.count(),
                "earnings": float(month_jobs.aggregate(total=Sum("total_amount"))["total"] or 0),
                "rating": round(float(month_rating), 1) if month_rating is not None else None,
            }
        )

    return {
        "period": "Overall" if period == "overall" else start_label(period),
        "completion_rate": completion_rate,
        "completed": completed,
        "total": total,
        "cancelled": cancelled,
        "open": total - completed - cancelled,
        "gross_revenue": f"{gross_revenue or 0:.2f}",
        "average_rating": round(float(rating["average"]), 1) if rating["average"] is not None else None,
        "review_count": rating["count"],
        # The penalty system does not exist yet; null tells the app to hide the tile.
        "penalties": None,
        "penalty_amount": None,
        "needs_attention": total >= 3 and completion_rate < 50,
        "trend": trend,
    }


def start_label(period):
    return timezone.datetime.strptime(period, "%Y-%m").strftime("%b %Y")


def get_technician_earnings(*, user, period="overall"):
    """Completed jobs with what the customer paid online and what the technician collected on site.

    Commission and payouts are not modelled yet, so amounts are job values, not take-home pay.
    """
    from apps.payments.models import Payment, PaymentProvider, PaymentType

    jobs = (
        Booking.objects.filter(assigned_technician=user, booking_status__in=COMPLETED_STATUSES)
        .select_related("service")
        .prefetch_related(
            Prefetch(
                "payments",
                queryset=Payment.objects.filter(provider=PaymentProvider.OFFLINE, payment_type=PaymentType.BALANCE).order_by("-created_at"),
                to_attr="offline_balance_payments",
            )
        )
        .order_by("-completed_at", "-service_date")
    )
    if period != "overall":
        try:
            start = timezone.datetime.strptime(period, "%Y-%m").date()
        except ValueError as exc:
            raise serializers.ValidationError({"period": "Use 'overall' or YYYY-MM."}) from exc
        jobs = jobs.filter(service_date__gte=start, service_date__lt=_month_start(start, -1))

    rows = []
    for job in jobs:
        payment = job.offline_balance_payments[0] if job.offline_balance_payments else None
        rows.append(
            {
                "id": str(job.id),
                "booking_number": job.booking_number,
                "service_name": job.service.name,
                "service_date": job.service_date,
                "completed_at": job.completed_at,
                "total_amount": job.total_amount,
                "paid_online": job.advance_paid,
                "collected_by_you": job.balance_collected,
                "collection_method": (payment.provider_payload or {}).get("method", "") if payment else "",
            }
        )
    return {
        "period": "Overall" if period == "overall" else start_label(period),
        "job_count": len(rows),
        "job_value_total": sum((row["total_amount"] for row in rows), Decimal("0.00")),
        "collected_by_you_total": sum((row["collected_by_you"] for row in rows), Decimal("0.00")),
        "paid_online_total": sum((row["paid_online"] for row in rows), Decimal("0.00")),
        "jobs": rows,
    }
