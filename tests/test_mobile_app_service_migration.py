import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_services_are_classified_for_mobile_app_in_first_match_order():
    previous = ("catalogue", "0018_blogpost")
    target = ("catalogue", "0020_seed_mobile_app_service_fields")
    executor = MigrationExecutor(connection)
    executor.migrate([previous])

    old_apps = executor.loader.project_state([previous]).apps
    Category = old_apps.get_model("catalogue", "ServiceCategory")
    Service = old_apps.get_model("catalogue", "Service")
    general_category = Category.objects.create(name="General Services", slug="general-services")
    cleaning_category = Category.objects.create(name="Cleaning", slug="cleaning")
    chimney_category = Category.objects.create(name="Chimney", slug="chimney")

    samples = (
        ("Water Tank Cleaning", "water-tank-cleaning", general_category, "water-tank"),
        ("Split AC Service", "split-ac-service", general_category, "ac"),
        ("Dishwasher Repair", "dishwasher-repair", general_category, "dishwasher"),
        ("RO Water Purifier", "ro-water-purifier", general_category, "water-purifier"),
        ("Routine Home Service", "routine-home-service", chimney_category, "chimney"),
        ("Bathroom Cleaning", "bathroom-cleaning", cleaning_category, ""),
    )
    ids_by_slug = {}
    for name, slug, category, _ in samples:
        service = Service.objects.create(
            category=category,
            name=name,
            slug=slug,
            base_price="100.00",
            advance_amount="20.00",
            estimated_duration_minutes=30,
        )
        ids_by_slug[slug] = service.pk

    MigrationExecutor(connection).migrate([target])
    latest_apps = MigrationExecutor(connection).loader.project_state([target]).apps
    MigratedService = latest_apps.get_model("catalogue", "Service")
    try:
        for _, slug, _, expected_category in samples:
            service = MigratedService.objects.get(pk=ids_by_slug[slug])
            assert service.app_category == expected_category
            assert service.show_in_app is bool(expected_category)
    finally:
        latest_executor = MigrationExecutor(connection)
        latest_executor.migrate(latest_executor.loader.graph.leaf_nodes())
