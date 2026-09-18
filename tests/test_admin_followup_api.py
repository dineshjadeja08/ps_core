from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.bookings.models import BookingStatus, PaymentStatus
from apps.catalogue.models import Package, PackageItem
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent, NotificationStatus
from apps.operations.models import Lead, LeadStatus
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType
from apps.technicians.models import TechnicianLeave
from tests.factories import (
    address_factory,
    booking_factory,
    service_area_factory,
    service_factory,
    slot_factory,
    technician_factory,
    user_factory,
)


@pytest.fixture
def admin_user():
    return user_factory("+919640000001", role=UserRole.ADMIN, is_staff=True)


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def service():
    return service_factory()


@pytest.mark.django_db
def test_admin_can_filter_and_review_technician_leave(
    django_capture_on_commit_callbacks,
    admin_client,
    admin_user,
):
    technician = technician_factory(phone_number="+919640000002", code="TECH-LEAVE")
    leave = TechnicianLeave.objects.create(
        technician=technician,
        start_at=timezone.now() + timedelta(days=1),
        end_at=timezone.now() + timedelta(days=2),
        reason="Family event",
    )

    pending = admin_client.get(
        "/api/v1/admin/technician-leaves/",
        {"technician": str(technician.id), "status": "PENDING"},
    )
    with django_capture_on_commit_callbacks(execute=True):
        approved = admin_client.post(
            f"/api/v1/admin/technician-leaves/{leave.id}/approve/",
            {"note": "Coverage arranged."},
            format="json",
        )

    assert pending.status_code == 200
    assert pending.json()["count"] == 1
    assert pending.json()["results"][0]["status"] == "PENDING"
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    leave.refresh_from_db()
    assert leave.approved_by == admin_user
    assert leave.review_note == "Coverage arranged."
    assert AuditLog.objects.filter(action=AuditAction.TECHNICIAN_LEAVE_APPROVED, resource_id=str(leave.id)).exists()

    with django_capture_on_commit_callbacks(execute=True):
        rejected = admin_client.post(
            f"/api/v1/admin/technician-leaves/{leave.id}/reject/",
            {"note": "Peak-day staffing required."},
            format="json",
        )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["review_note"] == "Peak-day staffing required."
    assert AuditLog.objects.filter(action=AuditAction.TECHNICIAN_LEAVE_REJECTED, resource_id=str(leave.id)).exists()


@pytest.mark.django_db
def test_non_admin_cannot_review_technician_leave(service):
    customer = user_factory("+919640000003")
    technician = technician_factory(phone_number="+919640000004", code="TECH-NOADMIN")
    leave = TechnicianLeave.objects.create(
        technician=technician,
        start_at=timezone.now() + timedelta(days=1),
        end_at=timezone.now() + timedelta(days=2),
        reason="Personal",
    )
    client = APIClient()
    client.force_authenticate(user=customer)

    response = client.post(f"/api/v1/admin/technician-leaves/{leave.id}/approve/", {}, format="json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_package_crud_with_service_quantities(
    django_capture_on_commit_callbacks,
    admin_client,
    service,
):
    second_service = service_factory(category=service.category, slug="ac-gas-refill")
    payload = {
        "name": "Pre-Summer AC Bundle",
        "slug": "pre-summer-ac-bundle",
        "description": "Three AC services at a bundle price.",
        "bundle_price": "2499.00",
        "valid_from": str(timezone.localdate()),
        "valid_until": str(timezone.localdate() + timedelta(days=60)),
        "maximum_usage_limit": 3,
        "is_active": True,
        "items": [
            {"service": str(service.id), "quantity": 2, "display_order": 1},
            {"service": str(second_service.id), "quantity": 1, "display_order": 2},
        ],
    }

    with django_capture_on_commit_callbacks(execute=True):
        created = admin_client.post("/api/v1/admin/packages/", payload, format="json")

    assert created.status_code == 201
    package_id = created.json()["id"]
    assert created.json()["items"][0]["quantity"] == 2
    assert PackageItem.objects.filter(package_id=package_id).count() == 2
    assert AuditLog.objects.filter(action=AuditAction.PACKAGE_CREATED, resource_id=package_id).exists()

    with django_capture_on_commit_callbacks(execute=True):
        updated = admin_client.patch(
            f"/api/v1/admin/packages/{package_id}/",
            {
                "bundle_price": "2299.00",
                "items": [{"service": str(service.id), "quantity": 3, "display_order": 1}],
            },
            format="json",
        )

    assert updated.status_code == 200
    assert updated.json()["bundle_price"] == "2299.00"
    assert PackageItem.objects.get(package_id=package_id).quantity == 3
    assert AuditLog.objects.filter(action=AuditAction.PACKAGE_UPDATED, resource_id=package_id).exists()

    listed = admin_client.get("/api/v1/admin/packages/", {"is_active": "true"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    with django_capture_on_commit_callbacks(execute=True):
        deleted = admin_client.delete(f"/api/v1/admin/packages/{package_id}/")
    assert deleted.status_code == 204
    assert not Package.objects.filter(id=package_id).exists()
    assert AuditLog.objects.filter(action=AuditAction.PACKAGE_DELETED, resource_id=package_id).exists()


@pytest.mark.django_db
def test_package_rejects_empty_items_and_invalid_validity(admin_client):
    invalid_dates = admin_client.post(
        "/api/v1/admin/packages/",
        {
            "name": "Invalid bundle",
            "slug": "invalid-bundle",
            "bundle_price": "100.00",
            "valid_from": "2026-10-02",
            "valid_until": "2026-10-01",
            "maximum_usage_limit": 1,
            "items": [],
        },
        format="json",
    )

    empty_items = admin_client.post(
        "/api/v1/admin/packages/",
        {
            "name": "Empty bundle",
            "slug": "empty-bundle",
            "bundle_price": "100.00",
            "maximum_usage_limit": 1,
            "items": [],
        },
        format="json",
    )

    assert invalid_dates.status_code == 400
    assert "valid_until" in invalid_dates.json()["error"]["details"]
    assert empty_items.status_code == 400
    assert "items" in empty_items.json()["error"]["details"]


@pytest.mark.django_db
def test_dashboard_summary_uses_database_aggregates_beyond_first_page(admin_client, service):
    customer = user_factory("+919640000005")
    service_area = service_area_factory()
    address = address_factory(customer)
    slot = slot_factory(service_area, days=2)
    booking = booking_factory(
        customer,
        service,
        address,
        slot,
        booking_status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.UNPAID,
        advance_paid=Decimal("0.00"),
    )
    technician_factory(phone_number="+919640000006", code="TECH-DASH", service_area=service_area)
    Lead.objects.bulk_create(
        [
            Lead(
                customer_name=f"Lead {index}",
                primary_mobile=f"+91965{index:07d}",
                status=LeadStatus.NEW,
            )
            for index in range(55)
        ]
    )
    Payment.objects.create(
        booking=booking,
        provider=PaymentProvider.OFFLINE,
        amount=Decimal("399.00"),
        payment_type=PaymentType.BOOKING_ADVANCE,
        status=PaymentRecordStatus.SUCCESS,
        paid_at=timezone.now(),
    )
    Notification.objects.create(
        booking=booking,
        event=NotificationEvent.PAYMENT_FAILED,
        channel=NotificationChannel.WHATSAPP,
        status=NotificationStatus.FAILED,
        title="Payment failed",
        message="Please retry.",
    )

    response = admin_client.get("/api/v1/admin/dashboard/summary/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["leads_today"] == 55
    assert payload["open_unassigned_leads_count"] == 55
    assert payload["active_bookings_count"] == 1
    assert payload["available_technicians_count"] == 1
    assert payload["unassigned_bookings"] == 1
    assert payload["daily_gmv"] == "399.00"
    assert payload["revenue_today"] == "399.00"
    assert payload["failed_notifications"] == 1
