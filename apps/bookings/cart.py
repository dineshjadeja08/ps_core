from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import CartItem, BookingStatus, PaymentStatus
from apps.bookings.idempotency import begin_checkout_request, complete_checkout_request
from apps.bookings.serializers import BookingCreateSerializer, BookingSerializer
from apps.bookings.services import create_booking
from apps.catalogue.models import Service
from apps.operations.services import mark_cart_added
from common.idempotency import idempotency_key_from_request, request_fingerprint


class CartAddSerializer(serializers.Serializer):
    service_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
    merge = serializers.BooleanField(default=False)
    booking_ids = serializers.DictField(child=serializers.UUIDField(), required=False, default=dict)


class CartResponseSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField(), read_only=True)
    count = serializers.IntegerField(read_only=True)
    total = serializers.CharField(read_only=True)
    advance_total = serializers.CharField(read_only=True)
    unavailable_service_ids = serializers.ListField(child=serializers.UUIDField(), required=False)


class CartCheckoutResponseSerializer(serializers.Serializer):
    bookings = BookingSerializer(many=True, read_only=True)
    cart = CartResponseSerializer(read_only=True)


class CartCheckoutSerializer(serializers.Serializer):
    items = BookingCreateSerializer(many=True, allow_empty=False)

    def validate_items(self, value):
        ids = [item["service_id"] for item in value]
        if len(ids) > 100 or len(ids) != len(set(ids)):
            raise serializers.ValidationError("Choose up to 100 different services.")
        return value


def lock_customer(customer):
    # Serialize all cart writes for this account, including concurrent device checkouts.
    get_user_model().objects.select_for_update().get(pk=customer.pk)


def cart_response(customer):
    CartItem.objects.filter(
        customer=customer, booking__payment_status__in=[PaymentStatus.PARTIALLY_PAID, PaymentStatus.PAID],
        booking__advance_paid__gte=F("booking__advance_required"),
    ).delete()
    rows = CartItem.objects.filter(customer=customer).select_related("service__category", "booking")
    items = []
    total = Decimal("0.00")
    advance = Decimal("0.00")
    for row in rows:
        service = row.service
        price = row.booking.total_amount if row.booking_id else service.effective_price
        deposit = row.booking.advance_required if row.booking_id else service.advance_amount
        available = service.is_active and service.category.is_active
        total += price
        advance += deposit
        items.append({
            "id": str(service.id), "slug": service.slug, "name": service.name,
            "price": str(price), "advance": str(deposit), "available": available,
            "bookingId": str(row.booking_id) if row.booking_id else None,
        })
    return {"items": items, "count": len(items), "total": str(total), "advance_total": str(advance)}


class CartView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CartResponseSerializer, tags=["Cart"])
    @transaction.atomic
    def get(self, request):
        lock_customer(request.user)
        return Response(cart_response(request.user))

    @extend_schema(request=CartAddSerializer, responses=CartResponseSerializer, tags=["Cart"])
    @transaction.atomic
    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lock_customer(request.user)
        ids = set(serializer.validated_data["service_ids"])
        services = list(Service.objects.filter(id__in=ids, is_active=True, category__is_active=True))
        if len(services) != len(ids) and not serializer.validated_data["merge"]:
            raise serializers.ValidationError("One or more services are unavailable. Remove them and try again.")
        existing = set(CartItem.objects.filter(customer=request.user).values_list("service_id", flat=True))
        if len(existing | {service.id for service in services}) > 100:
            raise serializers.ValidationError("Your cart can contain up to 100 services.")
        for service in services:
            row, created = CartItem.objects.get_or_create(customer=request.user, service=service)
            if created:
                mark_cart_added(customer=request.user, service=service, request=request)
            booking_id = serializer.validated_data["booking_ids"].get(str(service.id))
            if booking_id and not row.booking_id:
                from apps.bookings.models import Booking
                booking = Booking.objects.filter(id=booking_id, customer=request.user, service=service).first()
                if booking is None:
                    raise serializers.ValidationError("A saved booking could not be verified.")
                row.booking = booking
                row.save(update_fields=["booking", "updated_at"])
        result = cart_response(request.user)
        result["unavailable_service_ids"] = [str(value) for value in ids - {service.id for service in services}]
        return Response(result)


class CartItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CartResponseSerializer, tags=["Cart"])
    @transaction.atomic
    def delete(self, request, service_id):
        lock_customer(request.user)
        CartItem.objects.filter(customer=request.user, service_id=service_id).delete()
        return Response(cart_response(request.user))


class CartCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CartCheckoutSerializer, responses=CartCheckoutResponseSerializer, tags=["Cart"])
    @transaction.atomic
    def post(self, request):
        serializer = CartCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lock_customer(request.user)
        fingerprint = request_fingerprint(request.data)
        idempotency_key = idempotency_key_from_request(request, fallback=f"cart-{fingerprint}")
        checkout_request, previous_bookings = begin_checkout_request(
            customer=request.user,
            key=idempotency_key,
            fingerprint=fingerprint,
        )
        if previous_bookings:
            return Response(
                {
                    "bookings": BookingSerializer(previous_bookings, many=True).data,
                    "cart": cart_response(request.user),
                }
            )
        selections = serializer.validated_data["items"]
        rows = {row.service_id: row for row in CartItem.objects.filter(customer=request.user).select_related("booking")}
        # Lock slot rows in deterministic order before creating any booking.
        from apps.scheduling.models import TimeSlot
        list(TimeSlot.objects.select_for_update().filter(id__in=[item["slot_id"] for item in selections]).order_by("id"))
        bookings = []
        for selection in selections:
            row = rows.get(selection["service_id"])
            if row is None:
                raise serializers.ValidationError("A selected service is no longer in your cart. Refresh and try again.")
            if row.booking_id:
                if row.booking.booking_status not in [BookingStatus.PENDING_PAYMENT, BookingStatus.PAYMENT_FAILED]:
                    raise serializers.ValidationError("A cart booking has already changed. Refresh your cart before continuing.")
                booking = row.booking
            else:
                booking = create_booking(customer=request.user, **selection)
                row.booking = booking
                row.save(update_fields=["booking", "updated_at"])
            bookings.append(booking)
        complete_checkout_request(checkout_request, bookings)
        return Response({"bookings": BookingSerializer(bookings, many=True).data, "cart": cart_response(request.user)})
