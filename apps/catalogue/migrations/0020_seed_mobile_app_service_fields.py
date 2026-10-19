import re

from django.db import migrations


APP_CATEGORY_RULES = (
    ("water-tank", re.compile(r"tank", re.IGNORECASE)),
    ("sofa", re.compile(r"sofa|upholster", re.IGNORECASE)),
    ("mosquito-net", re.compile(r"mosquito", re.IGNORECASE)),
    ("chimney", re.compile(r"chimney", re.IGNORECASE)),
    ("dishwasher", re.compile(r"dishwasher", re.IGNORECASE)),
    ("washing-machine", re.compile(r"washing|washer|laundry", re.IGNORECASE)),
    ("refrigerator", re.compile(r"fridge|refrigerator", re.IGNORECASE)),
    ("water-purifier", re.compile(r"purifier|\bro\b", re.IGNORECASE)),
    ("geyser", re.compile(r"geyser|heater", re.IGNORECASE)),
    ("microwave", re.compile(r"microwave|oven", re.IGNORECASE)),
    ("cctv", re.compile(r"cctv", re.IGNORECASE)),
    ("tv", re.compile(r"\btv\b|television", re.IGNORECASE)),
    ("ac", re.compile(r"\bac\b|air conditioner", re.IGNORECASE)),
)


def category_for_text(value):
    for category, pattern in APP_CATEGORY_RULES:
        if pattern.search(value or ""):
            return category
    return ""


def seed_mobile_app_fields(apps, schema_editor):
    Service = apps.get_model("catalogue", "Service")
    pending_updates = []
    services = Service.objects.select_related("category").all().iterator(chunk_size=500)

    for service in services:
        category = category_for_text(f"{service.name} {service.slug}")
        if not category:
            category = category_for_text(service.category.name)
        if category:
            service.show_in_app = True
            service.app_category = category
            pending_updates.append(service)

    if pending_updates:
        Service.objects.bulk_update(pending_updates, ("show_in_app", "app_category"), batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0019_service_mobile_app_fields")]

    operations = [migrations.RunPython(seed_mobile_app_fields, migrations.RunPython.noop)]
