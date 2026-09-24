from django.db import migrations


LAUNCH_CITIES = ("Chennai", "Coimbatore")


def deactivate_non_launch_cities(apps, schema_editor):
    ServiceArea = apps.get_model("locations", "ServiceArea")
    ServiceArea.objects.exclude(city__in=LAUNCH_CITIES).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0002_servicearea_services"),
    ]

    operations = [
        migrations.RunPython(deactivate_non_launch_cities, migrations.RunPython.noop),
    ]
