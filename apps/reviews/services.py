from django.db import transaction
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus
from apps.reviews.models import Review


@transaction.atomic
def create_review(*, booking_id, customer, rating, comment):
    try:
        booking = Booking.objects.select_for_update().get(id=booking_id, customer=customer)
    except Booking.DoesNotExist as exc:
        raise serializers.ValidationError("Booking was not found.") from exc

    if booking.booking_status != BookingStatus.COMPLETED:
        raise serializers.ValidationError("Only completed bookings can be reviewed.")
    if Review.objects.filter(booking=booking).exists():
        raise serializers.ValidationError("Booking has already been reviewed.")

    return Review.objects.create(
        booking=booking,
        customer=customer,
        technician=booking.assigned_technician,
        rating=rating,
        comment=comment,
    )
