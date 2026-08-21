from datetime import time, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.catalogue.models import AdvancePaymentType, Service, ServiceCategory, ServiceImage
from apps.locations.models import Address, ServiceArea
from apps.scheduling.models import TimeSlot


def png_upload(name):
    image = Image.new("RGB", (1, 1), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def customer():
    return User.objects.create_user("+919876543210", role=UserRole.CUSTOMER, is_verified=True)


@pytest.fixture
def technician():
    return User.objects.create_user("+919876543211", role=UserRole.TECHNICIAN, is_verified=True)


@pytest.fixture
def admin_user():
    return User.objects.create_user("+919876543299", role=UserRole.ADMIN, is_verified=True, is_staff=True)


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def customer_client(customer):
    client = APIClient()
    client.force_authenticate(user=customer)
    return client


@pytest.fixture
def technician_client(technician):
    client = APIClient()
    client.force_authenticate(user=technician)
    return client


@pytest.fixture
def category():
    return ServiceCategory.objects.create(
        name="AC Service",
        slug="ac-service",
        description="Routine AC services.",
        display_order=1,
    )


@pytest.fixture
def service(category):
    return Service.objects.create(
        category=category,
        name="AC General Service",
        slug="ac-general-service",
        short_description="Cleaning and inspection.",
        description="A complete AC cleaning service.",
        base_price=Decimal("1499.00"),
        advance_amount=Decimal("299.00"),
        estimated_duration_minutes=90,
        is_featured=True,
        is_active=True,
    )


def service_payload(category, **overrides):
    payload = {
        "category": str(category.id),
        "name": "AC Deep Cleaning",
        "slug": "ac-deep-cleaning",
        "short_description": "Professional AC deep-cleaning service.",
        "description": "Full service description.",
        "base_price": "899.00",
        "selling_price": "699.00",
        "advance_payment_type": AdvancePaymentType.FIXED,
        "advance_payment_value": "199.00",
        "estimated_duration_minutes": 60,
        "is_featured": True,
        "is_popular": True,
        "is_active": True,
        "display_order": 2,
    }
    payload.update(overrides)
    return payload


def create_booking(customer, service):
    service_area = ServiceArea.objects.create(
        name="Tirupattur Central",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )
    address = Address.objects.create(
        customer=customer,
        label="Home",
        recipient_name="Dinesh",
        phone="+919876543210",
        address_line_1="12 Main Road",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )
    slot = TimeSlot.objects.create(
        service_area=service_area,
        date=timezone.localdate() + timedelta(days=1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        capacity=2,
    )
    return Booking.objects.create(
        booking_number="PS-ADM001",
        customer=customer,
        service=service,
        address=address,
        address_snapshot={"postal_code": "635601"},
        service_date=slot.date,
        time_slot=slot,
        problem_description="AC is not cooling.",
        subtotal=Decimal("1499.00"),
        total_amount=Decimal("1499.00"),
        advance_required=Decimal("299.00"),
        advance_paid=Decimal("299.00"),
        balance_due=Decimal("1200.00"),
        booking_status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.PARTIALLY_PAID,
    )


@pytest.mark.django_db
def test_admin_can_create_service(admin_client, category):
    response = admin_client.post("/api/v1/admin/services/", service_payload(category), format="json")

    assert response.status_code == 201
    service = Service.objects.get(slug="ac-deep-cleaning")
    assert service.selling_price == Decimal("699.00")
    assert service.advance_amount == Decimal("199.00")
    assert service.is_popular is True


@pytest.mark.django_db
def test_admin_can_edit_service_and_change_price(admin_client, service):
    response = admin_client.patch(
        f"/api/v1/admin/services/{service.id}/",
        {
            "base_price": "1599.00",
            "selling_price": "1299.00",
            "short_description": "Updated short copy.",
            "description": "Updated full copy.",
            "advance_payment_type": AdvancePaymentType.PERCENTAGE,
            "advance_payment_value": "10.00",
        },
        format="json",
    )

    assert response.status_code == 200
    service.refresh_from_db()
    assert service.base_price == Decimal("1599.00")
    assert service.selling_price == Decimal("1299.00")
    assert service.advance_amount == Decimal("129.90")
    assert service.description == "Updated full copy."


@pytest.mark.django_db
def test_admin_can_upload_cover_image(admin_client, service):
    image = png_upload("cover.png")

    response = admin_client.patch(
        f"/api/v1/admin/services/{service.id}/",
        {"cover_image": image},
        format="multipart",
    )

    assert response.status_code == 200
    service.refresh_from_db()
    assert service.cover_image.name.startswith("services/covers/")


@pytest.mark.django_db
def test_admin_can_activate_and_deactivate_service(admin_client, service):
    response = admin_client.patch(f"/api/v1/admin/services/{service.id}/", {"is_active": False}, format="json")

    assert response.status_code == 200
    service.refresh_from_db()
    assert service.is_active is False


@pytest.mark.django_db
def test_admin_can_manage_category(admin_client):
    create = admin_client.post(
        "/api/v1/admin/service-categories/",
        {
            "name": "Appliance Repair",
            "slug": "appliance-repair",
            "description": "Repair services.",
            "display_order": 4,
            "is_active": True,
        },
        format="json",
    )
    category_id = create.json()["id"]
    update = admin_client.patch(
        f"/api/v1/admin/service-categories/{category_id}/",
        {"description": "Updated repair services.", "display_order": 3},
        format="json",
    )

    assert create.status_code == 201
    assert update.status_code == 200
    category = ServiceCategory.objects.get(id=category_id)
    assert category.description == "Updated repair services."
    assert category.display_order == 3


@pytest.mark.django_db
def test_non_admins_cannot_access_admin_catalogue(customer_client, technician_client, category):
    customer_response = customer_client.post("/api/v1/admin/services/", service_payload(category), format="json")
    technician_response = technician_client.post("/api/v1/admin/services/", service_payload(category), format="json")

    assert customer_response.status_code == 403
    assert technician_response.status_code == 403


@pytest.mark.django_db
def test_customer_endpoint_reflects_admin_updates(admin_client, client, service):
    admin_client.patch(
        f"/api/v1/admin/services/{service.id}/",
        {
            "short_description": "Freshly updated.",
            "selling_price": "999.00",
            "is_popular": True,
        },
        format="json",
    )

    response = client.get(f"/api/v1/services/{service.slug}/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["short_description"] == "Freshly updated."
    assert payload["selling_price"] == "999.00"
    assert payload["effective_price"] == 999.0 or payload["effective_price"] == "999.00"
    assert payload["is_popular"] is True


@pytest.mark.django_db
def test_inactive_service_hidden_from_customer_listing(admin_client, client, service):
    admin_client.patch(f"/api/v1/admin/services/{service.id}/", {"is_active": False}, format="json")

    response = client.get("/api/v1/services/")

    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_existing_booking_snapshot_unchanged_after_price_update(admin_client, customer, service):
    booking = create_booking(customer, service)

    response = admin_client.patch(
        f"/api/v1/admin/services/{service.id}/",
        {"base_price": "1899.00", "advance_payment_value": "399.00"},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.subtotal == Decimal("1499.00")
    assert booking.total_amount == Decimal("1499.00")
    assert booking.advance_required == Decimal("299.00")


@pytest.mark.django_db
def test_invalid_price_and_advance_percentage_rejected(admin_client, category):
    negative = admin_client.post(
        "/api/v1/admin/services/",
        service_payload(category, base_price="-1.00"),
        format="json",
    )
    percentage = admin_client.post(
        "/api/v1/admin/services/",
        service_payload(
            category,
            slug="bad-advance-percent",
            advance_payment_type=AdvancePaymentType.PERCENTAGE,
            advance_payment_value="120.00",
        ),
        format="json",
    )

    assert negative.status_code == 400
    assert percentage.status_code == 400


@pytest.mark.django_db
def test_admin_can_add_and_remove_gallery_image(admin_client, service):
    image = png_upload("gallery.png")

    create = admin_client.post(
        f"/api/v1/admin/services/{service.id}/images/",
        {"image": image, "alt_text": "AC unit", "display_order": 1},
        format="multipart",
    )
    image_id = create.json()["id"]
    delete = admin_client.delete(f"/api/v1/admin/services/{service.id}/images/{image_id}/")

    assert create.status_code == 201
    assert delete.status_code == 204
    assert ServiceImage.objects.count() == 0


@pytest.mark.django_db
def test_service_with_booking_is_soft_deleted(admin_client, customer, service):
    create_booking(customer, service)

    response = admin_client.delete(f"/api/v1/admin/services/{service.id}/")

    assert response.status_code == 204
    service.refresh_from_db()
    assert service.is_active is False


@pytest.mark.django_db
def test_catalogue_changes_are_audited(django_capture_on_commit_callbacks, admin_client, service):
    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.patch(
            f"/api/v1/admin/services/{service.id}/",
            {"base_price": "1599.00"},
            format="json",
        )

    assert response.status_code == 200
    assert AuditLog.objects.filter(action=AuditAction.SERVICE_PRICE_CHANGED, resource_id=str(service.id)).exists()
