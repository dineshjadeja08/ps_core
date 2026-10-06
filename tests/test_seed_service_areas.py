import pytest
from django.core.management import call_command

from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import ServiceArea, ServiceAreaLocality
from apps.locations.service_area_data import CHENNAI_LOCALITIES, CHENNAI_SERVICE_AREAS, COIMBATORE_SERVICE_AREAS


@pytest.mark.django_db
def test_seed_service_areas_adds_chennai_coverage_and_preserves_existing_areas():
    existing = ServiceArea.objects.create(
        name="Existing operational area",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )

    call_command("seed_service_areas", keep_existing_active=True, verbosity=0)

    assert ServiceArea.objects.filter(city="Chennai", is_active=True).count() == len(CHENNAI_SERVICE_AREAS)
    assert ServiceArea.objects.filter(city="Coimbatore", is_active=True).count() == len(COIMBATORE_SERVICE_AREAS)
    assert ServiceArea.objects.get(postal_code="600001").name == "Broadway / George Town / Mannadi / Parry's Corner"
    assert ServiceArea.objects.get(postal_code="600040").name == "Anna Nagar / Thirumangalam"
    assert ServiceAreaLocality.objects.filter(service_area__city="Chennai", is_active=True).count() == len(CHENNAI_LOCALITIES)
    assert set(ServiceAreaLocality.objects.filter(service_area__postal_code="600001").values_list("name", flat=True)) == {
        "Broadway", "George Town", "Mannadi", "Parry's Corner"
    }
    existing.refresh_from_db()
    assert existing.is_active is True


@pytest.mark.django_db
def test_seed_service_areas_enables_every_active_service_for_each_launch_pincode():
    category = ServiceCategory.objects.create(name="Home services", slug="home-services")
    active_service = Service.objects.create(
        category=category,
        name="Active service",
        slug="active-service",
        base_price="500.00",
        advance_amount="100.00",
        estimated_duration_minutes=60,
    )
    inactive_service = Service.objects.create(
        category=category,
        name="Inactive service",
        slug="inactive-service",
        base_price="500.00",
        advance_amount="100.00",
        estimated_duration_minutes=60,
        is_active=False,
    )

    call_command("seed_service_areas", keep_existing_active=True, verbosity=0)

    chennai_areas = ServiceArea.objects.filter(city="Chennai", is_active=True)
    assert chennai_areas.count() == len(CHENNAI_SERVICE_AREAS)
    assert not chennai_areas.exclude(services=active_service).exists()
    assert not chennai_areas.filter(services=inactive_service).exists()
    assert not chennai_areas.filter(services_configured=True).exists()
