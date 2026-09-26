import pytest
from django.core.management import call_command

from apps.locations.models import ServiceArea
from apps.locations.service_area_data import CHENNAI_SERVICE_AREAS, COIMBATORE_SERVICE_AREAS


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
    existing.refresh_from_db()
    assert existing.is_active is True
