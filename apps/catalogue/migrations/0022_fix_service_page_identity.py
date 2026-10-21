from django.db import migrations


def fix_service_identity(apps, schema_editor):
    Service = apps.get_model("catalogue", "Service")
    Service.objects.filter(slug="general-ac-service").update(
        short_description=(
            "Routine AC cleaning and performance checks for filters, coils, drainage, "
            "and an accessible outdoor unit."
        )
    )
    Service.objects.filter(slug="services").update(slug="ac-chemical-wash")
    Service.objects.filter(slug="chimney-cleaning-services").update(name="Chimney Cleaning Service")
    Service.objects.filter(slug="refrigerator-repair-services").update(name="Refrigerator Repair Inspection")
    Service.objects.filter(slug="washing-machine-repair-service").update(name="Washing Machine Repair Inspection")


def reverse_service_identity(apps, schema_editor):
    Service = apps.get_model("catalogue", "Service")
    Service.objects.filter(slug="general-ac-service").update(
        short_description="Combo package for AC installation with full chemical wash."
    )
    Service.objects.filter(slug="ac-chemical-wash").update(slug="services")
    Service.objects.filter(slug="chimney-cleaning-services").update(name="Chimney Inspection")
    Service.objects.filter(slug="refrigerator-repair-services").update(name="Refrigerator Inspection")
    Service.objects.filter(slug="washing-machine-repair-service").update(
        name="Washing Machine Repair Inspection Charge"
    )


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0021_fix_public_seo_names_and_blog_slugs")]

    operations = [migrations.RunPython(fix_service_identity, reverse_service_identity)]
