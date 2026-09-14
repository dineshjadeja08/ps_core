from django.utils import timezone
from rest_framework import serializers

from apps.bookings.models import Booking, CheckoutRequest


def begin_checkout_request(*, customer, key: str, fingerprint: str) -> tuple[CheckoutRequest, list[Booking]]:
    record, _ = CheckoutRequest.objects.get_or_create(
        customer=customer,
        idempotency_key=key,
        defaults={"request_fingerprint": fingerprint},
    )
    record = CheckoutRequest.objects.select_for_update().get(pk=record.pk)
    if record.request_fingerprint != fingerprint:
        raise serializers.ValidationError(
            {"idempotency_key": "This Idempotency-Key was already used for a different checkout request."}
        )
    if not record.completed_at:
        return record, []

    bookings_by_id = {
        str(booking.id): booking
        for booking in Booking.objects.filter(customer=customer, id__in=record.booking_ids)
        .select_related("service", "time_slot")
        .prefetch_related("status_history")
    }
    bookings = [bookings_by_id[booking_id] for booking_id in record.booking_ids if booking_id in bookings_by_id]
    if len(bookings) != len(record.booking_ids):
        raise serializers.ValidationError("A previous checkout result could not be restored. Please contact support.")
    return record, bookings


def complete_checkout_request(record: CheckoutRequest, bookings: list[Booking]) -> None:
    record.booking_ids = [str(booking.id) for booking in bookings]
    record.completed_at = timezone.now()
    record.save(update_fields=["booking_ids", "completed_at", "updated_at"])
