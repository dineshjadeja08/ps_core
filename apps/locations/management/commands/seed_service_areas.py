from django.core.management.base import BaseCommand

from apps.locations.models import ServiceArea
from apps.locations.service_area_data import LAUNCH_SERVICE_AREAS


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

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(LAUNCH_SERVICE_AREAS)} active service areas for Chennai and Coimbatore."
            )
        )
