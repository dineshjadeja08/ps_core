from decimal import Decimal

from django.db import migrations


def map_populated_catalogue(apps, schema_editor):
    Category = apps.get_model("catalogue", "ServiceCategory")
    Service = apps.get_model("catalogue", "Service")
    ServiceArea = apps.get_model("locations", "ServiceArea")
    if not Service.objects.exists():
        return

    category_specs = [
        ("ac-services", "AC", "AC repair, cleaning, installation, uninstallation and gas services.", 1),
        ("washing-machine-services", "Washing Machine", "Washing machine repair, installation and uninstallation.", 2),
        ("refrigerator-services", "Refrigerator", "Refrigerator inspection, installation and uninstallation.", 3),
    ]
    categories = {}
    for slug, name, description, order in category_specs:
        category, _ = Category.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "description": description, "display_order": order, "is_active": True},
        )
        categories[slug] = category

    specs = [
        ("ac-service", "AC Repairs", "ac-services", "Repair & Services", "AC issue diagnosis and repair estimate.", "Issue diagnosis\nBasic inspection\nRepair estimate before work", "499.00", 1),
        ("foam-jet-ac-service", "AC Foam Jet Clean", "ac-services", "Repair & Services", "Foam jet cleaning for accessible AC parts.", "Filter cleaning\nFoam jet coil cleaning\nDrainage and cooling check", "999.00", 2),
        ("full-ac-chemical-wash", "AC Chemical Wash", "ac-services", "Repair & Services", "Deep chemical cleaning for reduced airflow.", "Indoor unit chemical cleaning\nFilter and drain tray wash\nCooling test", "2499.00", 3),
        ("ac-repair-gas-refill", "AC Gas Refill", "ac-services", "Gas Refill", "Cooling diagnosis and gas refill after approval.", "Cooling diagnosis\nLeakage check guidance\nGas refill\nPerformance test", "2799.00", 4),
        ("ac-installation", "AC Installation", "ac-services", "Install & Uninstall", "Standard split AC installation and testing.", "Indoor unit mounting\nConnection and drainage check\nCooling test", "1899.00", 5),
        ("ac-uninstallation", "AC Uninstallation", "ac-services", "Install & Uninstall", "Safe AC disconnection and removal.", "Gas lock where possible\nIndoor and outdoor unit removal\nBasic handover", "999.00", 6),
        ("washing-machine-repair-service", "Washing Machine Repair", "washing-machine-services", "Repair & Services", "Diagnosis for washing, spinning and draining issues.", "Issue diagnosis\nBasic inspection\nRepair estimate before work", "449.00", 1),
        ("washing-machine-installation", "Washing Machine Installation", "washing-machine-services", "Install & Uninstall", "Install and test a compatible washing machine.", "Machine placement\nInlet and drain connection\nBasic function test", "599.00", 2),
        ("washing-machine-uninstallation", "Washing Machine Uninstallation", "washing-machine-services", "Install & Uninstall", "Disconnect and prepare a washing machine for shifting.", "Water inlet disconnection\nDrain disconnection\nSafe handover", "499.00", 3),
        ("refrigerator-repair-services", "Refrigerator Inspection", "refrigerator-services", "Repair & Services", "Inspection for cooling, leakage, noise and electrical issues.", "Issue diagnosis\nBasic external inspection\nRepair estimate before work", "499.00", 1),
        ("refrigerator-installation-uninstallation", "Refrigerator Installation / Uninstallation", "refrigerator-services", "Install & Uninstall", "Position, connect or safely disconnect a refrigerator.", "Placement guidance\nPower and leveling check\nBasic cooling test or safe disconnection", "699.00", 2),
    ]
    affected_ids = []
    for slug, name, category_slug, group, short, included, price, order in specs:
        service, created = Service.objects.get_or_create(
            slug=slug,
            defaults={
                "category": categories[category_slug],
                "name": name,
                "short_description": short,
                "description": short,
                "whats_included": included,
                "base_price": Decimal(price),
                "advance_amount": Decimal("99.00"),
                "advance_payment_type": "FIXED",
                "advance_payment_value": Decimal("99.00"),
                "estimated_duration_minutes": 60,
                "is_active": True,
                "display_order": order,
                "landing_group": group,
            },
        )
        if not created:
            service.category = categories[category_slug]
            service.name = name
            service.landing_group = group
            service.display_order = order
            service.is_active = True
            if not service.short_description:
                service.short_description = short
            if not service.whats_included:
                service.whats_included = included
            service.save(update_fields=["category", "name", "landing_group", "display_order", "is_active", "short_description", "whats_included", "updated_at"])
        affected_ids.append(service.id)

    for area in ServiceArea.objects.filter(is_active=True).iterator():
        area.services.add(*affected_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0006_service_landing_group"),
        ("locations", "0002_servicearea_services"),
    ]

    operations = [migrations.RunPython(map_populated_catalogue, migrations.RunPython.noop)]
