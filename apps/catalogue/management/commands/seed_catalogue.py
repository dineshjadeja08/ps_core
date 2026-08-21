from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalogue.models import Service, ServiceCategory


class Command(BaseCommand):
    help = "Seed development service categories and AC services."

    def handle(self, *args, **options):
        category_data = [
            ("AC Service", "ac-service", "Routine AC cleaning and maintenance.", 1),
            ("AC Repair", "ac-repair", "Diagnosis and repair for AC issues.", 2),
            ("Installation", "installation", "AC installation and setup.", 3),
            ("Uninstallation", "uninstallation", "Safe AC removal services.", 4),
            ("Gas Refill", "gas-refill", "Cooling gas inspection and refill.", 5),
            ("Inspection", "inspection", "Technician inspection and estimate.", 6),
        ]
        categories = {}
        for name, slug, description, display_order in category_data:
            category, _ = ServiceCategory.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                    "display_order": display_order,
                    "is_active": True,
                },
            )
            categories[slug] = category

        service_data = [
            {
                "category": "ac-service",
                "name": "AC General Service",
                "slug": "ac-general-service",
                "short_description": "Cleaning and inspection for split AC units.",
                "description": "Includes filter cleaning, coil inspection, drainage check, and basic performance review.",
                "base_price": Decimal("1499.00"),
                "advance_amount": Decimal("299.00"),
                "estimated_duration_minutes": 90,
                "is_featured": True,
            },
            {
                "category": "ac-repair",
                "name": "AC Repair Visit",
                "slug": "ac-repair-visit",
                "short_description": "Technician diagnosis for cooling, noise, and leakage issues.",
                "description": "Includes diagnosis and repair estimate. Parts and major work are billed separately.",
                "base_price": Decimal("699.00"),
                "advance_amount": Decimal("199.00"),
                "estimated_duration_minutes": 60,
                "is_featured": True,
            },
            {
                "category": "gas-refill",
                "name": "AC Gas Refill",
                "slug": "ac-gas-refill",
                "short_description": "Gas pressure check and refill for eligible units.",
                "description": "Technician checks leakage indicators and refills gas where appropriate.",
                "base_price": Decimal("2499.00"),
                "advance_amount": Decimal("499.00"),
                "estimated_duration_minutes": 120,
                "is_featured": False,
            },
        ]
        for service in service_data:
            Service.objects.update_or_create(
                slug=service["slug"],
                defaults={
                    **service,
                    "category": categories[service["category"]],
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("Seeded catalogue data."))
