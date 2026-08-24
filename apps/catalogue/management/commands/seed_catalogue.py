from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalogue.models import Service, ServiceCategory


class Command(BaseCommand):
    help = "Seed development service categories and AC services."

    def handle(self, *args, **options):
        category_data = [
            {
                "name": "AC Service",
                "slug": "ac-service",
                "description": "Cleaning, maintenance, and performance care for split and window AC units.",
                "display_order": 1,
            },
            {
                "name": "AC Repair",
                "slug": "ac-repair",
                "description": "Diagnosis and repair for cooling, leakage, noise, and power issues.",
                "display_order": 2,
            },
            {
                "name": "AC Installation",
                "slug": "ac-installation",
                "description": "Safe AC installation, removal, and relocation support.",
                "display_order": 3,
            },
            {
                "name": "Gas Refill",
                "slug": "gas-refill",
                "description": "Gas pressure checks, leak inspection, and eligible AC gas refilling.",
                "display_order": 4,
            },
            {
                "name": "Inspection",
                "slug": "inspection",
                "description": "Technician visit for issue inspection, diagnosis, and service estimate.",
                "display_order": 5,
            },
        ]
        categories = {}
        for item in category_data:
            category, _ = ServiceCategory.objects.update_or_create(
                slug=item["slug"],
                defaults={
                    "name": item["name"],
                    "description": item["description"],
                    "display_order": item["display_order"],
                    "is_active": True,
                },
            )
            categories[item["slug"]] = category

        service_data = [
            {
                "category": "ac-service",
                "name": "AC Deep Cleaning",
                "slug": "ac-deep-cleaning",
                "short_description": "Complete indoor and outdoor AC cleaning for fresher airflow.",
                "description": (
                    "A detailed AC cleaning service for homes that need better airflow, less dust, and improved cooling comfort. "
                    "The technician cleans key accessible parts, checks drainage, and reviews basic performance before completion."
                ),
                "whats_included": "Indoor unit filter cleaning\nCooling coil surface cleaning\nOutdoor unit dust removal\nDrain tray and pipe check\nBasic cooling performance review",
                "whats_excluded": "Gas charging\nSpare parts\nPCB, compressor, fan motor, or capacitor replacement\nDuct cleaning or civil work",
                "important_notes": "Power and water access are required. Final pricing for extra repair work is confirmed by the technician before proceeding.",
                "base_price": Decimal("899.00"),
                "selling_price": Decimal("699.00"),
                "advance_amount": Decimal("199.00"),
                "estimated_duration_minutes": 75,
                "is_featured": True,
                "is_popular": True,
                "display_order": 1,
            },
            {
                "category": "ac-service",
                "name": "AC General Service",
                "slug": "ac-general-service",
                "short_description": "Routine cleaning and inspection for regular AC maintenance.",
                "description": (
                    "Best for periodic maintenance before or during summer. The visit focuses on basic cleaning, visible checks, "
                    "drainage inspection, and guidance if deeper repair or gas work is needed."
                ),
                "whats_included": "Filter cleaning\nIndoor unit inspection\nOutdoor unit visual check\nDrainage check\nBasic cooling test",
                "whats_excluded": "Deep jet cleaning\nGas refill\nReplacement parts\nMajor repair work",
                "important_notes": "Recommended every 3 to 6 months depending on usage and dust levels.",
                "base_price": Decimal("599.00"),
                "selling_price": Decimal("499.00"),
                "advance_amount": Decimal("149.00"),
                "estimated_duration_minutes": 45,
                "is_featured": True,
                "is_popular": True,
                "display_order": 2,
            },
            {
                "category": "ac-repair",
                "name": "AC Not Cooling Repair",
                "slug": "ac-not-cooling-repair",
                "short_description": "Diagnosis for poor cooling, warm air, or frequent cut-off issues.",
                "description": (
                    "A focused repair visit for AC units that are running but not cooling properly. The technician checks common causes "
                    "such as clogged filters, low gas symptoms, outdoor unit issues, sensor behavior, and electrical faults."
                ),
                "whats_included": "Cooling issue diagnosis\nFilter and airflow check\nOutdoor unit inspection\nRepair estimate\nMinor adjustment where possible",
                "whats_excluded": "Gas refill\nLeak repair\nSpare parts\nMajor electrical or compressor work",
                "important_notes": "If parts, gas refill, or leak fixing are required, the technician will share the cost before starting extra work.",
                "base_price": Decimal("699.00"),
                "selling_price": Decimal("599.00"),
                "advance_amount": Decimal("199.00"),
                "estimated_duration_minutes": 60,
                "is_featured": True,
                "is_popular": True,
                "display_order": 1,
            },
            {
                "category": "ac-repair",
                "name": "AC Water Leakage Repair",
                "slug": "ac-water-leakage-repair",
                "short_description": "Fix dripping water, blocked drain pipe, and indoor leakage issues.",
                "description": (
                    "For indoor units leaking water or dripping near walls. The technician checks drain pipe blockage, tray alignment, "
                    "ice formation symptoms, and installation slope where accessible."
                ),
                "whats_included": "Leakage diagnosis\nDrain pipe cleaning check\nDrain tray inspection\nBasic alignment check\nRepair estimate",
                "whats_excluded": "Concealed pipe replacement\nWall repair\nGas refill\nMajor installation correction",
                "important_notes": "Some leakage problems may need additional pipe or installation work after inspection.",
                "base_price": Decimal("799.00"),
                "selling_price": Decimal("649.00"),
                "advance_amount": Decimal("199.00"),
                "estimated_duration_minutes": 60,
                "is_featured": False,
                "is_popular": True,
                "display_order": 2,
            },
            {
                "category": "ac-installation",
                "name": "Standard AC Installation",
                "slug": "ac-installation-standard",
                "short_description": "Wall-mounted split AC installation with basic setup checks.",
                "description": (
                    "Professional installation for a split AC unit at a prepared location. The technician mounts the indoor and outdoor units, "
                    "connects standard piping, checks drainage, and verifies basic cooling after installation."
                ),
                "whats_included": "Indoor unit mounting\nOutdoor unit placement guidance\nStandard copper pipe connection check\nDrain pipe setup\nCooling test",
                "whats_excluded": "Wall core cutting\nExtra copper pipe\nOutdoor stand\nElectrical wiring upgrades\nGas top-up if required",
                "important_notes": "Site readiness, wall condition, and extra material needs are confirmed during the visit.",
                "base_price": Decimal("1799.00"),
                "selling_price": Decimal("1499.00"),
                "advance_amount": Decimal("399.00"),
                "estimated_duration_minutes": 150,
                "is_featured": True,
                "is_popular": False,
                "display_order": 1,
            },
            {
                "category": "ac-installation",
                "name": "AC Uninstallation",
                "slug": "ac-uninstallation",
                "short_description": "Safe removal of split AC indoor and outdoor units.",
                "description": (
                    "Careful AC removal for shifting, renovation, or replacement. The technician disconnects the unit, protects reusable parts, "
                    "and keeps the system ready for relocation where possible."
                ),
                "whats_included": "Indoor unit removal\nOutdoor unit removal\nPipe disconnection\nBasic packing guidance\nSite cleanup after removal",
                "whats_excluded": "Transport\nReinstallation\nWall repair\nAdditional gas recovery equipment where not supported",
                "important_notes": "Customer should keep original packing materials ready if the unit needs to be transported.",
                "base_price": Decimal("999.00"),
                "selling_price": Decimal("799.00"),
                "advance_amount": Decimal("249.00"),
                "estimated_duration_minutes": 90,
                "is_featured": False,
                "is_popular": False,
                "display_order": 2,
            },
            {
                "category": "gas-refill",
                "name": "AC Gas Refill",
                "slug": "ac-gas-refill",
                "short_description": "Gas pressure check and refill for eligible AC units.",
                "description": (
                    "For AC units showing low gas symptoms after inspection. The technician checks pressure, looks for visible leakage signs, "
                    "and refills gas where the unit is eligible and safe to proceed."
                ),
                "whats_included": "Gas pressure check\nVisible leakage indicator check\nEligible gas refill\nCooling test after refill",
                "whats_excluded": "Major leak repair\nCopper pipe replacement\nCompressor repair\nParts replacement",
                "important_notes": "Gas refill is done only after inspection. Leak repair, if needed, is quoted separately.",
                "base_price": Decimal("2499.00"),
                "selling_price": Decimal("2199.00"),
                "advance_amount": Decimal("499.00"),
                "estimated_duration_minutes": 120,
                "is_featured": False,
                "is_popular": True,
                "display_order": 1,
            },
            {
                "category": "inspection",
                "name": "AC Inspection Visit",
                "slug": "ac-inspection-visit",
                "short_description": "Technician diagnosis and estimate before repair or replacement.",
                "description": (
                    "A practical inspection visit when the issue is unclear. The technician reviews the AC condition, identifies likely causes, "
                    "and explains the next best service or repair estimate."
                ),
                "whats_included": "On-site diagnosis\nVisible component inspection\nIssue explanation\nRepair or service estimate",
                "whats_excluded": "Repair work\nParts\nGas refill\nDeep cleaning",
                "important_notes": "Inspection charges cover diagnosis only. Any additional work is approved separately.",
                "base_price": Decimal("399.00"),
                "selling_price": Decimal("299.00"),
                "advance_amount": Decimal("99.00"),
                "estimated_duration_minutes": 45,
                "is_featured": False,
                "is_popular": False,
                "display_order": 1,
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
