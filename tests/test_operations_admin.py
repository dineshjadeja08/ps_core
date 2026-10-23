from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth.models import Permission
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, RequestFactory
from django.utils import timezone
from PIL import Image

from apps.accounts.models import UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.catalogue.models import ServiceCategory
from apps.operations.admin import LeadAdmin
from apps.operations.models import FAQ, HomepageBanner, Lead, LeadSource, LeadStatus, LeadStatusHistory
from apps.operations.serializers import LeadPaymentLinkSerializer, LeadSerializer
from apps.operations.services import mark_booking_payment_paid
from tests.factories import address_factory, booking_factory, service_area_factory, service_factory, slot_factory, user_factory


def png_upload(name="banner.png"):
    image = Image.new("RGB", (8, 8), color="purple")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def staff_user():
    return user_factory("+919620000001", role=UserRole.ADMIN, is_staff=True, is_verified=True)


@pytest.mark.django_db
def test_active_duplicate_lead_is_rejected():
    Lead.objects.create(
        customer_name="Ravi",
        primary_mobile="+919876543210",
        source=LeadSource.PHONE,
        status=LeadStatus.NEW,
    )

    with pytest.raises(ValidationError):
        Lead.objects.create(
            customer_name="Ravi Again",
            primary_mobile="+919876543210",
            source=LeadSource.WHATSAPP,
            status=LeadStatus.FOLLOW_UP,
        )


@pytest.mark.django_db
def test_closed_lead_allows_new_active_lead():
    Lead.objects.create(
        customer_name="Closed Lead",
        primary_mobile="+919876543210",
        source=LeadSource.PHONE,
        status=LeadStatus.CLOSED,
    )

    lead = Lead.objects.create(
        customer_name="Fresh Lead",
        primary_mobile="+919876543210",
        source=LeadSource.WEBSITE,
        status=LeadStatus.NEW,
    )

    assert lead.status == LeadStatus.NEW


@pytest.mark.django_db
def test_admin_lead_save_records_history_and_audit(django_capture_on_commit_callbacks, staff_user):
    request = RequestFactory().post("/admin/operations/lead/add/")
    request.user = staff_user
    lead = Lead(
        customer_name="Manual Customer",
        primary_mobile="+919876543211",
        source=LeadSource.MANUAL,
        status=LeadStatus.NEW,
    )

    with django_capture_on_commit_callbacks(execute=True):
        LeadAdmin(Lead, AdminSite()).save_model(request, lead, form=None, change=False)

    assert lead.created_by == staff_user
    assert LeadStatusHistory.objects.filter(lead=lead, to_status=LeadStatus.NEW, changed_by=staff_user).exists()
    assert AuditLog.objects.filter(action=AuditAction.LEAD_CREATED, resource_id=str(lead.id)).exists()


@pytest.mark.django_db
def test_banner_schedule_and_url_validation():
    now = timezone.now()
    banner = HomepageBanner(
        title="Summer service",
        description="AC and appliance care",
        desktop_image=png_upload(),
        image_alt_text="Purple Squad technician",
        button_text="Book now",
        button_link="/services",
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
    )
    banner.full_clean()
    assert banner.is_live is True

    banner.ends_at = now - timedelta(days=1)
    with pytest.raises(ValidationError):
        banner.full_clean()

    banner.ends_at = now + timedelta(hours=1)
    banner.button_link = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        banner.full_clean()


@pytest.mark.django_db
def test_active_faq_uniqueness_by_context():
    category = ServiceCategory.objects.create(name="Cleaning", slug="cleaning")
    service = service_factory(category=category, slug="bathroom-cleaning")
    FAQ.objects.create(question="What is included?", answer="Cleaning checklist.", category=category, service=service)

    with pytest.raises(Exception):
        FAQ.objects.create(question="What is included?", answer="Duplicate.", category=category, service=service)


@pytest.mark.django_db
def test_admin_dashboard_shows_operations_metrics(staff_user):
    staff_user.user_permissions.add(Permission.objects.get(content_type__app_label="operations", codename="view_lead"))
    Lead.objects.create(customer_name="Dashboard Lead", primary_mobile="+919876543212", status=LeadStatus.NEW)
    client = Client()
    client.force_login(staff_user)

    response = client.get("/admin/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Operations Dashboard" in content
    assert "New leads" in content


@pytest.mark.django_db
def test_setup_staff_groups_command_creates_expected_groups():
    call_command("setup_staff_groups", verbosity=0)

    from django.contrib.auth.models import Group

    assert Group.objects.filter(name="Operations Admin").exists()
    assert Group.objects.filter(name="Catalogue Manager").exists()
    assert Group.objects.get(name="Finance").permissions.filter(codename="view_payment").exists()


@pytest.mark.django_db
def test_lead_serializer_returns_multiple_selected_service_lines_and_totals():
    category = ServiceCategory.objects.create(name="Appliance Care", slug="appliance-care")
    primary = service_factory(category=category, slug="ac-primary")
    extra = service_factory(category=category, slug="ac-extra")
    lead = Lead.objects.create(
        customer_name="Ravi",
        primary_mobile="+919876543219",
        required_service=primary,
        service_items=[{"service_id": str(primary.id), "quantity": 1}, {"service_id": str(extra.id), "quantity": 2}],
        source=LeadSource.ONCALL,
    )

    payload = LeadSerializer(lead).data

    assert [(item["service_id"], item["quantity"]) for item in payload["line_items"]] == [
        (str(primary.id), 1), (str(extra.id), 2)
    ]
    assert payload["subtotal"] == Decimal("4497.00")
    assert payload["total_amount"] == Decimal("4497.00")


@pytest.mark.django_db
def test_lead_service_items_must_match_primary_service_category():
    first_category = ServiceCategory.objects.create(name="AC", slug="ac")
    other_category = ServiceCategory.objects.create(name="TV", slug="tv")
    primary = service_factory(category=first_category, slug="ac-primary-check")
    other = service_factory(category=other_category, slug="tv-extra-check")
    serializer = LeadSerializer(data={
        "customer_name": "Ravi",
        "primary_mobile": "+919876543218",
        "required_service": str(primary.id),
        "service_items": [{"service_id": str(primary.id), "quantity": 1}, {"service_id": str(other.id), "quantity": 1}],
    })

    assert not serializer.is_valid()
    assert "service_items" in serializer.errors


def test_whatsapp_payment_link_requires_customer_consent():
    serializer = LeadPaymentLinkSerializer(data={"channel": "WHATSAPP", "payment_scope": "FULL"})

    assert not serializer.is_valid()
    assert "whatsapp_consent_confirmed" in serializer.errors


@pytest.mark.django_db
def test_paid_admin_lead_is_linked_as_a_manual_work_order():
    customer = user_factory("+919876543217")
    service = service_factory(slug="admin-paid-lead")
    area = service_area_factory()
    booking = booking_factory(customer, service, address_factory(customer), slot_factory(area))
    lead = Lead.objects.create(
        customer=customer,
        customer_name="Ravi",
        primary_mobile=customer.phone_number,
        required_service=service,
        source=LeadSource.ONCALL,
        pending_booking=booking,
    )

    result = mark_booking_payment_paid(booking=booking, performed_by=None)
    booking.refresh_from_db()

    assert result.status == LeadStatus.CONVERTED
    assert result.converted_booking_id == booking.id
    assert result.payment_status == "PAID"
    assert booking.is_manual_work_order is True
