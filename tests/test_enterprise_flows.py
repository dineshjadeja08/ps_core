import hmac
import json
from decimal import Decimal
from hashlib import sha256

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.payments.models import Payment, PaymentRecordStatus
from apps.payments.services import make_payment_signature
from apps.reviews.models import Review
from apps.technicians.models import TechnicianAssignment
from tests.factories import (
    address_factory,
    booking_factory,
    booking_payload,
    service_area_factory,
    service_factory,
    slot_factory,
    technician_factory,
    user_factory,
)


@pytest.fixture
def customer():
    return user_factory("+919876543210")


@pytest.fixture
def other_customer():
    return user_factory("+919876543211")


@pytest.fixture
def admin_user():
    return user_factory("+919876543299", role=UserRole.ADMIN, is_staff=True)


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
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def booking_context(customer):
    service_area = service_area_factory()
    service = service_factory()
    address = address_factory(customer)
    slot = slot_factory(service_area)
    return {
        "service_area": service_area,
        "service": service,
        "address": address,
        "slot": slot,
    }


def create_booking_via_api(client, context):
    return client.post(
        "/api/v1/bookings/",
        booking_payload(context["service"], context["address"], context["slot"]),
        format="json",
    )


def pay_booking_advance(client, booking_id):
    order = client.post(f"/api/v1/bookings/{booking_id}/payments/order/").json()
    payment_id = f"pay_{booking_id.hex[:10]}"
    signature = make_payment_signature(order["provider_order_id"], payment_id)
    return client.post(
        "/api/v1/payments/verify/",
        {
            "razorpay_order_id": order["provider_order_id"],
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
        format="json",
    )


@pytest.mark.django_db
def test_new_customer_booking_payment_confirmed_flow(customer_client, booking_context):
    create_response = create_booking_via_api(customer_client, booking_context)
    booking_id = create_response.json()["id"]

    payment_response = pay_booking_advance(customer_client, Booking.objects.get(id=booking_id).id)

    booking = Booking.objects.get(id=booking_id)
    assert create_response.status_code == 201
    assert payment_response.status_code == 200
    assert booking.booking_status == BookingStatus.CONFIRMED
    assert booking.payment_status == PaymentStatus.PARTIALLY_PAID
    assert booking.advance_paid == Decimal("299.00")


@pytest.mark.django_db
def test_two_customers_compete_for_final_slot(customer_client, other_customer_client, booking_context, other_customer):
    booking_context["slot"].capacity = 1
    booking_context["slot"].save()
    other_address = address_factory(other_customer)

    first = create_booking_via_api(customer_client, booking_context)
    second = other_customer_client.post(
        "/api/v1/bookings/",
        booking_payload(booking_context["service"], other_address, booking_context["slot"]),
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_invalid_razorpay_signature_flow(customer_client, booking_context):
    booking_id = create_booking_via_api(customer_client, booking_context).json()["id"]
    order = customer_client.post(f"/api/v1/bookings/{booking_id}/payments/order/").json()

    response = customer_client.post(
        "/api/v1/payments/verify/",
        {
            "razorpay_order_id": order["provider_order_id"],
            "razorpay_payment_id": "pay_bad_signature",
            "razorpay_signature": "bad-signature",
        },
        format="json",
    )

    assert response.status_code == 400
    assert Payment.objects.get().status == PaymentRecordStatus.FAILED
    assert Booking.objects.get(id=booking_id).booking_status == BookingStatus.PENDING_PAYMENT


@pytest.mark.django_db
def test_duplicate_razorpay_webhook_flow(customer_client, booking_context, settings):
    booking_id = create_booking_via_api(customer_client, booking_context).json()["id"]
    order = customer_client.post(f"/api/v1/bookings/{booking_id}/payments/order/").json()
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_enterprise_webhook",
                        "order_id": order["provider_order_id"],
                        "amount": 29900,
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, sha256).hexdigest()
    client = APIClient()

    first = client.post(
        "/api/v1/payments/webhooks/razorpay/",
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
    )
    second = client.post(
        "/api/v1/payments/webhooks/razorpay/",
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
    )

    booking = Booking.objects.get(id=booking_id)
    assert first.status_code == 200
    assert second.status_code == 200
    assert booking.booking_status == BookingStatus.CONFIRMED
    assert Payment.objects.get().status == PaymentRecordStatus.SUCCESS


@pytest.mark.django_db
def test_customer_cannot_read_another_customers_booking(customer_client, other_customer_client, booking_context):
    booking_id = create_booking_via_api(customer_client, booking_context).json()["id"]

    response = other_customer_client.get(f"/api/v1/bookings/{booking_id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_admin_assigns_technician_flow(admin_client, customer, booking_context):
    booking = booking_factory(customer, booking_context["service"], booking_context["address"], booking_context["slot"])
    technician = technician_factory(service_area=booking_context["service_area"])

    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(technician.id), "notes": "Manual dispatch."},
        format="json",
    )

    booking.refresh_from_db()
    assert response.status_code == 200
    assert booking.assigned_technician_id == technician.user_id
    assert booking.booking_status == BookingStatus.TECHNICIAN_ASSIGNED
    assert TechnicianAssignment.objects.filter(booking=booking, unassigned_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_reassignment_flow(admin_client, customer, booking_context):
    booking = booking_factory(customer, booking_context["service"], booking_context["address"], booking_context["slot"])
    first = technician_factory(phone_number="+919876543301", code="TECH-FLOW1", service_area=booking_context["service_area"])
    second = technician_factory(phone_number="+919876543302", code="TECH-FLOW2", service_area=booking_context["service_area"])

    admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(first.id)},
        format="json",
    )
    response = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/assign-technician/",
        {"technician_id": str(second.id)},
        format="json",
    )

    booking.refresh_from_db()
    assert response.status_code == 200
    assert booking.assigned_technician_id == second.user_id
    assert TechnicianAssignment.objects.filter(booking=booking, unassigned_at__isnull=False).count() == 1


@pytest.mark.django_db
def test_booking_start_balance_collection_completion_flow(admin_client, customer, booking_context):
    technician = technician_factory(service_area=booking_context["service_area"])
    booking = booking_factory(
        customer,
        booking_context["service"],
        booking_context["address"],
        booking_context["slot"],
        booking_status=BookingStatus.TECHNICIAN_ASSIGNED,
        assigned_technician=technician.user,
    )

    start = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/start/", {}, format="json")
    balance = admin_client.post(
        f"/api/v1/admin/bookings/{booking.id}/record-balance/",
        {"amount": "1200.00", "method": "UPI"},
        format="json",
    )
    complete = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/complete/", {}, format="json")

    booking.refresh_from_db()
    assert start.status_code == 200
    assert balance.status_code == 200
    assert complete.status_code == 200
    assert booking.balance_collected == Decimal("1200.00")
    assert booking.payment_status == PaymentStatus.PAID
    assert booking.booking_status == BookingStatus.COMPLETED


@pytest.mark.django_db
def test_cancelled_booking_cannot_start(admin_client, customer, booking_context):
    technician = technician_factory(service_area=booking_context["service_area"])
    booking = booking_factory(
        customer,
        booking_context["service"],
        booking_context["address"],
        booking_context["slot"],
        booking_status=BookingStatus.CANCELLED,
        assigned_technician=technician.user,
    )

    response = admin_client.post(f"/api/v1/admin/bookings/{booking.id}/start/", {}, format="json")

    assert response.status_code == 400
    booking.refresh_from_db()
    assert booking.booking_status == BookingStatus.CANCELLED


@pytest.mark.django_db
def test_completed_booking_review_flow(customer_client, customer, booking_context):
    technician = technician_factory(service_area=booking_context["service_area"])
    booking = booking_factory(
        customer,
        booking_context["service"],
        booking_context["address"],
        booking_context["slot"],
        booking_status=BookingStatus.COMPLETED,
        payment_status=PaymentStatus.PAID,
        assigned_technician=technician.user,
        balance_collected=Decimal("1200.00"),
    )

    response = customer_client.post(
        f"/api/v1/bookings/{booking.id}/review/",
        {"rating": 5, "comment": "Excellent service."},
        format="json",
    )

    assert response.status_code == 201
    review = Review.objects.get(booking=booking)
    assert review.rating == 5
    assert review.technician == technician.user


@pytest.mark.django_db
def test_openapi_schema_contains_critical_paths():
    response = APIClient().get("/api/schema/", HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    schema = json.loads(response.content)
    paths = schema["paths"]
    assert "/api/v1/bookings/" in paths
    assert "/api/v1/bookings/{booking_id}/payments/order/" in paths
    assert "/api/v1/payments/verify/" in paths
    assert "/api/v1/payments/webhooks/razorpay/" in paths
    assert "/api/v1/admin/bookings/{booking_id}/assign-technician/" in paths
    assert "/api/v1/admin/bookings/{booking_id}/record-balance/" in paths
    assert "/api/v1/bookings/{booking_id}/review/" in paths
