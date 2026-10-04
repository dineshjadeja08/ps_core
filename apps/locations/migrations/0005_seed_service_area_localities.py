from django.db import migrations
from django.utils.text import slugify

from apps.locations.service_area_data import CHENNAI_LOCALITIES


def seed_localities(apps, schema_editor):
    ServiceArea = apps.get_model("locations", "ServiceArea")
    ServiceAreaLocality = apps.get_model("locations", "ServiceAreaLocality")

    for display_order, (name, postal_code) in enumerate(CHENNAI_LOCALITIES):
        service_area = ServiceArea.objects.filter(country="India", postal_code=postal_code).first()
        if not service_area:
            continue
        ServiceAreaLocality.objects.update_or_create(
            service_area=service_area,
            slug=slugify(name),
            defaults={"name": name, "is_active": True, "display_order": display_order},
        )


class Migration(migrations.Migration):
    dependencies = [("locations", "0004_add_service_area_localities")]

    operations = [migrations.RunPython(seed_localities, migrations.RunPython.noop)]
