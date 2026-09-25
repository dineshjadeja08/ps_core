from io import BytesIO
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.audit.models import AuditLog
from apps.bookings.models import BookingStatus, PaymentStatus
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent
from apps.catalogue.models import ServiceCategory
from apps.operations.models import FAQ, HomepageBanner, HomepageBannerPlacement
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType
from apps.reviews.models import Review
from tests.factories import address_factory, booking_factory, service_area_factory, service_factory, slot_factory, user_factory


@pytest.fixture
def super_admin():
    return user_factory("+919630000001", role=UserRole.SUPER_ADMIN, is_staff=True, is_superuser=True)


@pytest.fixture
def admin_user():
    return user_factory("+919630000002", role=UserRole.ADMIN, is_staff=True)


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def super_admin_client(super_admin):
    client = APIClient()
    client.force_authenticate(user=super_admin)
    return client


@pytest.fixture
def booking():
    customer = user_factory("+919630000003", role=UserRole.CUSTOMER)
    service_area = service_area_factory(postal_code="600001", name="Chennai Central")
    service = service_factory(slug="ac-service-reports")
    address = address_factory(customer, postal_code="600001")
    slot = slot_factory(service_area)
    return booking_factory(customer, service, address, slot, booking_status=BookingStatus.COMPLETED, payment_status=PaymentStatus.PAID)


@pytest.mark.django_db
def test_admin_reports_summary(admin_client, booking):
    Payment.objects.create(
        booking=booking,
        provider=PaymentProvider.OFFLINE,
        amount=Decimal("1499.00"),
        payment_type=PaymentType.BALANCE,
        status=PaymentRecordStatus.SUCCESS,
    )

    response = admin_client.get("/api/v1/admin/reports/summary/")

    assert response.status_code == 200
    assert response.json()["completed_services"] == 1
    assert response.json()["revenue_collected"] == "1499.00"


@pytest.mark.django_db
def test_admin_settings_returns_safe_flags(admin_client):
    response = admin_client.get("/api/v1/admin/settings/")

    assert response.status_code == 200
    assert "razorpay_configured" in response.json()
    assert "cloudinary_media_enabled" in response.json()
    assert "cloudinary_media_configured" in response.json()
    assert "RAZORPAY_KEY_SECRET" not in str(response.json())
    assert "CLOUDINARY_API_SECRET" not in str(response.json())


@pytest.mark.django_db
def test_super_admin_can_list_staff_and_groups(super_admin_client, admin_user):
    Group.objects.create(name="Operations Admin")

    staff_response = super_admin_client.get("/api/v1/admin/staff/")
    group_response = super_admin_client.get("/api/v1/admin/staff-groups/")

    assert staff_response.status_code == 200
    assert any(item["id"] == str(admin_user.id) for item in staff_response.json()["results"])
    assert group_response.status_code == 200
    assert group_response.json()[0]["name"] == "Operations Admin"


@pytest.mark.django_db
def test_super_admin_can_create_admin_staff(
    django_capture_on_commit_callbacks,
    super_admin_client,
):
    group = Group.objects.create(name="Booking Managers")

    with django_capture_on_commit_callbacks(execute=True):
        response = super_admin_client.post(
            "/api/v1/admin/staff/",
            {
                "phone_number": "+919630000099",
                "password": "TemporaryPass123",
                "first_name": "Operations",
                "last_name": "Admin",
                "email": "operations@example.com",
                "role": "ADMIN",
                "group_ids": [group.id],
            },
            format="json",
        )

    assert response.status_code == 201, response.json()
    created = response.json()
    assert created["phone_number"] == "+919630000099"
    assert created["role"] == "ADMIN"
    assert created["is_staff"] is True
    assert created["is_verified"] is True
    assert created["groups"] == [{"id": group.id, "name": "Booking Managers"}]
    assert AuditLog.objects.filter(action="STAFF_CREATED", resource_id=created["id"]).exists()


@pytest.mark.django_db
def test_super_admin_can_update_staff_without_server_error(
    django_capture_on_commit_callbacks,
    super_admin_client,
    admin_user,
):
    group = Group.objects.create(name="Customer Support")

    with django_capture_on_commit_callbacks(execute=True):
        response = super_admin_client.patch(
            f"/api/v1/admin/staff/{admin_user.id}/",
            {"first_name": "Support", "group_ids": [group.id]},
            format="json",
        )

    assert response.status_code == 200, response.json()
    assert response.json()["id"] == str(admin_user.id)
    assert response.json()["first_name"] == "Support"
    assert response.json()["groups"] == [{"id": group.id, "name": "Customer Support"}]
    assert AuditLog.objects.filter(action="STAFF_UPDATED", resource_id=str(admin_user.id)).exists()


@pytest.mark.django_db
def test_customer_support_staff_has_scoped_admin_access():
    group = Group.objects.create(name="Customer Support")
    support_user = user_factory("+919630000088", role=UserRole.ADMIN, is_staff=True)
    support_user.groups.add(group)
    client = APIClient()
    client.force_authenticate(user=support_user)

    leads = client.get("/api/v1/admin/leads/")
    customers = client.get("/api/v1/admin/customers/")
    payments = client.get("/api/v1/admin/payments/")
    catalogue = client.get("/api/v1/admin/services/")

    assert leads.status_code == 200
    assert customers.status_code == 200
    assert payments.status_code == 403
    assert catalogue.status_code == 403


@pytest.mark.django_db
def test_super_admin_cannot_remove_own_access(super_admin_client, super_admin):
    response = super_admin_client.patch(
        f"/api/v1/admin/staff/{super_admin.id}/",
        {"role": "ADMIN", "is_staff": False},
        format="json",
    )

    assert response.status_code == 400
    super_admin.refresh_from_db()
    assert super_admin.role == UserRole.SUPER_ADMIN
    assert super_admin.is_staff is True


@pytest.mark.django_db
def test_regular_admin_cannot_create_staff(admin_client):
    response = admin_client.post(
        "/api/v1/admin/staff/",
        {
            "phone_number": "+919630000098",
            "password": "TemporaryPass123",
            "role": "ADMIN",
        },
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_can_list_audit_logs(admin_client, admin_user):
    AuditLog.objects.create(actor=admin_user, action="STAFF_UPDATED", resource_type="staff", resource_id=str(admin_user.id))

    response = admin_client.get("/api/v1/admin/audit-logs/?search=9630000002")

    assert response.status_code == 200
    assert response.json()["count"] == 1


@pytest.mark.django_db
def test_admin_can_manage_faqs(admin_client, booking):
    category = ServiceCategory.objects.create(name="FAQ Repair", slug="faq-repair")
    service = service_factory(category=category, slug="faq-repair-service")

    response = admin_client.post(
        "/api/v1/admin/faqs/",
        {
            "question": "Do you service AC?",
            "answer": "Yes.",
            "category": str(category.id),
            "service": str(service.id),
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201
    assert FAQ.objects.filter(question="Do you service AC?").exists()


@pytest.mark.django_db
def test_admin_can_manage_homepage_banners(admin_client):
    image_buffer = BytesIO()
    Image.new("RGB", (4, 4), color="purple").save(image_buffer, format="PNG")
    image = SimpleUploadedFile(
        "banner.png",
        image_buffer.getvalue(),
        content_type="image/png",
    )

    response = admin_client.post(
        "/api/v1/admin/homepage-banners/",
        {
            "title": "Summer service",
            "desktop_image": image,
            "image_alt_text": "Technician servicing appliance",
            "placement": HomepageBannerPlacement.MAIN,
            "is_active": True,
        },
        format="multipart",
    )

    assert response.status_code == 201, response.json()
    assert response.json()["title"] == "Summer service"


@pytest.mark.django_db
def test_public_homepage_banners_only_returns_live_active_banners():
    image_buffer = BytesIO()
    Image.new("RGB", (4, 4), color="purple").save(image_buffer, format="PNG")

    def banner_image(name):
        return SimpleUploadedFile(name, image_buffer.getvalue(), content_type="image/png")

    HomepageBanner.objects.create(
        title="Live banner",
        desktop_image=banner_image("live.png"),
        image_alt_text="Live promotion",
        placement=HomepageBannerPlacement.MAIN,
        is_active=True,
    )
    HomepageBanner.objects.create(
        title="Inactive banner",
        desktop_image=banner_image("inactive.png"),
        image_alt_text="Inactive promotion",
        placement=HomepageBannerPlacement.MAIN,
        is_active=False,
    )

    response = APIClient().get("/api/v1/homepage-banners/?placement=MAIN")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Live banner"]
    assert response.json()[0]["desktop_image_url"].startswith("http://testserver/")


@pytest.mark.django_db
def test_admin_can_moderate_reviews(admin_client, booking):
    review = Review.objects.create(
        booking=booking,
        customer=booking.customer,
        rating=5,
        comment="Good service.",
        is_visible=True,
    )

    list_response = admin_client.get("/api/v1/admin/reviews/")
    update_response = admin_client.patch(f"/api/v1/admin/reviews/{review.id}/", {"is_visible": False}, format="json")

    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert update_response.status_code == 200
    review.refresh_from_db()
    assert review.is_visible is False
