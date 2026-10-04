from django.core.management.base import BaseCommand

from django.utils.text import slugify

from apps.locations.models import ServiceArea, ServiceAreaLocality
from apps.locations.service_area_data import CHENNAI_LOCALITIES, LAUNCH_SERVICE_AREAS


class Command(BaseCommand):
    help = "Seed Purple Squad launch service areas for Chennai and Coimbatore."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-existing-active",
            action="store_true",
            help="Keep existing non-launch service areas active instead of deactivating them.",
        )

    def handle(self, *args, **options):
        launch_postal_codes = {postal_code for _, _, _, postal_code in LAUNCH_SERVICE_AREAS}

        if not options["keep_existing_active"]:
            ServiceArea.objects.exclude(postal_code__in=launch_postal_codes).update(is_active=False)

        for name, city, state, postal_code in LAUNCH_SERVICE_AREAS:
            ServiceArea.objects.update_or_create(
                country="India",
                postal_code=postal_code,
                defaults={
                    "name": name,
                    "city": city,
                    "state": state,
                    "is_active": True,
                },
            )

        for display_order, (name, postal_code) in enumerate(CHENNAI_LOCALITIES):
            service_area = ServiceArea.objects.get(country="India", postal_code=postal_code)
            ServiceAreaLocality.objects.update_or_create(
                service_area=service_area,
                slug=slugify(name),
                defaults={"name": name, "is_active": True, "display_order": display_order},
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(LAUNCH_SERVICE_AREAS)} active service areas for Chennai and Coimbatore."
            )
        )
