from datetime import timedelta
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
from apps.catalogue.models import ServiceCategory
from apps.operations.admin import LeadAdmin
from apps.operations.models import FAQ, HomepageBanner, Lead, LeadSource, LeadStatus, LeadStatusHistory
from tests.factories import service_factory, user_factory


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
