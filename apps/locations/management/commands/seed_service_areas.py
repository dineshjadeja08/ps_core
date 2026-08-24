from django.core.management.base import BaseCommand

from apps.locations.models import ServiceArea


LAUNCH_SERVICE_AREAS = [
    ("Chennai Central", "Chennai", "Tamil Nadu", "600001"),
    ("Chennai Egmore", "Chennai", "Tamil Nadu", "600008"),
    ("T Nagar", "Chennai", "Tamil Nadu", "600017"),
    ("Adyar", "Chennai", "Tamil Nadu", "600020"),
    ("Mylapore", "Chennai", "Tamil Nadu", "600004"),
    ("Anna Nagar", "Chennai", "Tamil Nadu", "600040"),
    ("Velachery", "Chennai", "Tamil Nadu", "600042"),
    ("OMR Thoraipakkam", "Chennai", "Tamil Nadu", "600096"),
    ("Medavakkam", "Chennai", "Tamil Nadu", "600100"),
    ("Bangalore Central", "Bangalore", "Karnataka", "560001"),
    ("Jayanagar", "Bangalore", "Karnataka", "560011"),
    ("Koramangala", "Bangalore", "Karnataka", "560034"),
    ("Indiranagar", "Bangalore", "Karnataka", "560038"),
    ("Marathahalli", "Bangalore", "Karnataka", "560037"),
    ("Whitefield", "Bangalore", "Karnataka", "560066"),
    ("Bannerghatta Road", "Bangalore", "Karnataka", "560076"),
    ("Electronic City", "Bangalore", "Karnataka", "560100"),
    ("Coimbatore Central", "Coimbatore", "Tamil Nadu", "641001"),
    ("RS Puram", "Coimbatore", "Tamil Nadu", "641002"),
    ("Peelamedu", "Coimbatore", "Tamil Nadu", "641004"),
    ("Gandhipuram", "Coimbatore", "Tamil Nadu", "641012"),
    ("Race Course", "Coimbatore", "Tamil Nadu", "641018"),
    ("Saravanampatti", "Coimbatore", "Tamil Nadu", "641035"),
    ("Saibaba Colony", "Coimbatore", "Tamil Nadu", "641011"),
    ("Vadavalli", "Coimbatore", "Tamil Nadu", "641041"),
]


class Command(BaseCommand):
    help = "Seed Purple Squad launch service areas for Chennai, Bangalore, and Coimbatore."

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
                f"Seeded {len(LAUNCH_SERVICE_AREAS)} active service areas for Chennai, Bangalore, and Coimbatore."
            )
        )
