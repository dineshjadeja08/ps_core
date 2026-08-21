import secrets
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.catalogue.models import Service
from apps.locations.models import Address
from apps.locations.services import get_active_service_area
from apps.notifications.models import NotificationEvent
from apps.notifications.services import emit_notification_event
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType
from apps.scheduling.models import TimeSlot
from apps.scheduling.services import SlotNotAvailable, lock_slot_for_reservation


ADMIN_CANCELLABLE_STATUSES = {
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.PAYMENT_FAILED,
    BookingStatus.CONFIRMED,
    BookingStatus.TECHNICIAN_ASSIGNED,
    BookingStatus.TECHNICIAN_EN_ROUTE,
    BookingStatus.IN_PROGRESS,
}
CUSTOMER_CANCELLABLE_STATUSES = {
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.CONFIRMED,
    BookingStatus.TECHNICIAN_ASSIGNED,
}
CUSTOMER_RESCHEDULABLE_STATUSES = {
    BookingStatus.CONFIRMED,
    BookingStatus.TECHNICIAN_ASSIGNED,
}
STARTABLE_STATUSES = {BookingStatus.TECHNICIAN_ASSIGNED, BookingStatus.TECHNICIAN_EN_ROUTE}
COMPLETABLE_STATUSES = {BookingStatus.IN_PROGRESS}


def create_booking(*, customer, service_id, address_id, slot_id, problem_description, customer_notes=""):
    with transaction.atomic():
        service = _get_active_service(service_id)
        address = _get_customer_address(customer, address_id)
        slot = _lock_and_validate_slot(slot_id=slot_id, address=address)

        booking = _create_booking_record(
            customer=customer,
            service=service,
            address=address,
            slot=slot,
            problem_description=problem_description,
            customer_notes=customer_notes,
        )
        BookingStatusHistory.objects.create(
            booking=booking,
            from_status="",
            to_status=BookingStatus.PENDING_PAYMENT,
            changed_by=customer,
            notes="Booking created.",
        )
        return booking


def _get_active_service(service_id):
    try:
        return Service.objects.select_related("category").get(
            id=service_id,
            is_active=True,
            category__is_active=True,
        )
    except Service.DoesNotExist as exc:
        raise serializers.ValidationError("Service is not available.") from exc


def _get_customer_address(customer, address_id):
    try:
        return Address.objects.get(id=address_id, customer=customer, is_active=True)
    except Address.DoesNotExist as exc:
        raise serializers.ValidationError("Address was not found.") from exc


def _lock_and_validate_slot(*, slot_id, address):
    service_area = get_active_service_area(address.postal_code)
    if service_area is None:
        raise serializers.ValidationError("Address is outside the active service area.")

    try:
        slot = lock_slot_for_reservation(slot_id)
    except TimeSlot.DoesNotExist as exc:
        raise serializers.ValidationError("Slot was not found.") from exc
    except SlotNotAvailable as exc:
        raise serializers.ValidationError("The selected slot is no longer available.") from exc

    if slot.service_area_id != service_area.id:
        raise serializers.ValidationError("Slot does not belong to the address service area.")
    return slot


def _create_booking_record(*, customer, service, address, slot, problem_description, customer_notes):
    subtotal = service.effective_price
    discount_amount = Decimal("0.00")
    tax_amount = Decimal("0.00")
    total_amount = subtotal - discount_amount + tax_amount
    advance_required = service.advance_amount
    advance_paid = Decimal("0.00")
    balance_due = total_amount - advance_paid

    for _ in range(5):
        try:
            return Booking.objects.create(
                booking_number=generate_booking_number(),
                customer=customer,
                service=service,
                address=address,
                address_snapshot=build_address_snapshot(address),
                service_date=slot.date,
                time_slot=slot,
                problem_description=problem_description,
                subtotal=subtotal,
                discount_amount=discount_amount,
                tax_amount=tax_amount,
                total_amount=total_amount,
                advance_required=advance_required,
                advance_paid=advance_paid,
                balance_due=balance_due,
                balance_collected=Decimal("0.00"),
                booking_status=BookingStatus.PENDING_PAYMENT,
                payment_status=PaymentStatus.UNPAID,
                customer_notes=customer_notes,
            )
        except IntegrityError:
            continue
    raise serializers.ValidationError("Could not generate a unique booking number.")


def build_address_snapshot(address):
    return {
        "recipient_name": address.recipient_name,
        "phone": address.phone,
        "address_line_1": address.address_line_1,
        "address_line_2": address.address_line_2,
        "landmark": address.landmark,
        "locality": address.locality,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "country": address.country,
        "latitude": str(address.latitude) if address.latitude is not None else None,
        "longitude": str(address.longitude) if address.longitude is not None else None,
    }


def generate_booking_number():
    return f"PS-{secrets.token_hex(3).upper()}"


@transaction.atomic
def start_booking(*, booking_id, changed_by, notes=""):
    booking = _lock_booking(booking_id)
    if booking.booking_status not in STARTABLE_STATUSES:
        raise serializers.ValidationError("Booking cannot be started from its current status.")
    if booking.assigned_technician_id is None:
        raise serializers.ValidationError("A technician must be assigned before starting the booking.")
    return _transition_booking(
        booking=booking,
        to_status=BookingStatus.IN_PROGRESS,
        changed_by=changed_by,
        notes=notes or "Booking started.",
    )


@transaction.atomic
def complete_booking(*, booking_id, changed_by, notes=""):
    booking = _lock_booking(booking_id)
    if booking.booking_status not in COMPLETABLE_STATUSES:
        raise serializers.ValidationError("Booking must be in progress before completion.")
    if booking.assigned_technician_id is None:
        raise serializers.ValidationError("A technician must be assigned before completion.")
    if settings.BOOKING_REQUIRE_BALANCE_BEFORE_COMPLETION and booking.balance_collected < booking.balance_due:
        raise serializers.ValidationError("Balance must be fully collected before completion.")

    previous_status = booking.booking_status
    booking.booking_status = BookingStatus.COMPLETED
    booking.completed_at = timezone.now()
    booking.save(update_fields=["booking_status", "completed_at", "updated_at"])
    _write_status_history(
        booking=booking,
        from_status=previous_status,
        to_status=BookingStatus.COMPLETED,
        changed_by=changed_by,
        notes=notes or "Booking completed.",
    )
    emit_notification_event(
        event=NotificationEvent.SERVICE_COMPLETED,
        recipient=booking.customer,
        booking=booking,
    )
    return booking


@transaction.atomic
def cancel_booking(*, booking_id, changed_by, notes="", actor="admin"):
    booking = _lock_booking(booking_id)
    allowed_statuses = ADMIN_CANCELLABLE_STATUSES if actor == "admin" else CUSTOMER_CANCELLABLE_STATUSES
    if booking.booking_status not in allowed_statuses:
        raise serializers.ValidationError("Booking cannot be cancelled from its current status.")
    if actor == "customer":
        _validate_policy_window(
            booking=booking,
            min_hours=settings.BOOKING_CUSTOMER_CANCEL_MIN_HOURS,
            message="Booking can no longer be cancelled online.",
        )

    previous_status = booking.booking_status
    booking.booking_status = BookingStatus.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["booking_status", "cancelled_at", "updated_at"])
    _write_status_history(
        booking=booking,
        from_status=previous_status,
        to_status=BookingStatus.CANCELLED,
        changed_by=changed_by,
        notes=notes or "Booking cancelled.",
    )
    emit_notification_event(
        event=NotificationEvent.BOOKING_CANCELLED,
        recipient=booking.customer,
        booking=booking,
        payload={"actor": actor},
    )
    return booking


@transaction.atomic
def reschedule_booking(*, booking_id, slot_id, changed_by, notes=""):
    booking = _lock_booking(booking_id)
    if booking.customer_id != changed_by.id:
        raise serializers.ValidationError("Booking was not found.")
    if booking.booking_status not in CUSTOMER_RESCHEDULABLE_STATUSES:
        raise serializers.ValidationError("Booking cannot be rescheduled from its current status.")
    _validate_policy_window(
        booking=booking,
        min_hours=settings.BOOKING_CUSTOMER_RESCHEDULE_MIN_HOURS,
        message="Booking can no longer be rescheduled online.",
    )

    slot = _lock_and_validate_slot(slot_id=slot_id, address=booking.address)
    previous_slot_id = str(booking.time_slot_id)
    previous_service_date = booking.service_date
    booking.time_slot = slot
    booking.service_date = slot.date
    booking.save(update_fields=["time_slot", "service_date", "updated_at"])
    BookingStatusHistory.objects.create(
        booking=booking,
        from_status=booking.booking_status,
        to_status=booking.booking_status,
        changed_by=changed_by,
        notes=notes
        or f"Booking rescheduled from {previous_service_date} slot {previous_slot_id} to {slot.date} slot {slot.id}.",
    )
    return booking


@transaction.atomic
def record_balance_collection(*, booking_id, amount, method, changed_by, notes=""):
    booking = _lock_booking(booking_id)
    if booking.booking_status not in {BookingStatus.IN_PROGRESS, BookingStatus.TECHNICIAN_ASSIGNED}:
        raise serializers.ValidationError("Balance can only be recorded for an active assigned booking.")
    remaining_balance = booking.balance_due - booking.balance_collected
    if amount <= Decimal("0.00"):
        raise serializers.ValidationError("Amount must be greater than zero.")
    if amount > remaining_balance:
        raise serializers.ValidationError("Amount cannot exceed the remaining balance.")

    payment = Payment.objects.create(
        booking=booking,
        provider=PaymentProvider.OFFLINE,
        amount=amount,
        currency="INR",
        payment_type=PaymentType.BALANCE,
        status=PaymentRecordStatus.SUCCESS,
        signature_verified=True,
        provider_payload={"method": method, "notes": notes},
        idempotency_key=f"offline-balance-{booking.id}-{timezone.now().timestamp()}",
        paid_at=timezone.now(),
    )
    booking.balance_collected += amount
    if booking.balance_collected >= booking.balance_due:
        booking.payment_status = PaymentStatus.PAID
    booking.save(update_fields=["balance_collected", "payment_status", "updated_at"])
    BookingStatusHistory.objects.create(
        booking=booking,
        from_status=booking.booking_status,
        to_status=booking.booking_status,
        changed_by=changed_by,
        notes=notes or f"Balance collection recorded via {method}.",
    )
    return booking, payment


def _lock_booking(booking_id):
    try:
        return Booking.objects.select_for_update().select_related("address", "time_slot").get(id=booking_id)
    except Booking.DoesNotExist as exc:
        raise serializers.ValidationError("Booking was not found.") from exc


def _transition_booking(*, booking, to_status, changed_by, notes):
    previous_status = booking.booking_status
    booking.booking_status = to_status
    booking.save(update_fields=["booking_status", "updated_at"])
    _write_status_history(
        booking=booking,
        from_status=previous_status,
        to_status=to_status,
        changed_by=changed_by,
        notes=notes,
    )
    return booking


def _write_status_history(*, booking, from_status, to_status, changed_by, notes):
    BookingStatusHistory.objects.create(
        booking=booking,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        notes=notes,
    )


def _validate_policy_window(*, booking, min_hours, message):
    service_start = timezone.make_aware(
        timezone.datetime.combine(booking.service_date, booking.time_slot.start_time),
        timezone.get_current_timezone(),
    )
    if service_start - timezone.now() < timezone.timedelta(hours=min_hours):
        raise serializers.ValidationError(message)
