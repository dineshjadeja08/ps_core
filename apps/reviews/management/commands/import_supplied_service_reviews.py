import re
from itertools import chain
from uuid import NAMESPACE_URL, uuid5

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalogue.models import Service
from apps.reviews.legacy_supplied_reviews import (
    AC_INSTALLATION_REVIEWS,
    AC_REMOVAL_REVIEWS,
    AC_REVIEWS,
    WASHING_REVIEWS,
)
from apps.reviews.models import Review
from apps.reviews.supplied_reviews import SERVICE_REVIEWS


SERVICE_ALIASES = {
    "Full AC Chemical Wash": "AC Chemical Wash",
    "AC Repair & Gas Refill": "AC Gas Refill",
    "Washing Machine Repair & Service": "Washing Machine Repair",
}
SLUG_ALIASES = {
    "full-ac-chemical-wash": "AC Chemical Wash",
    "ac-repair-gas-refill": "AC Gas Refill",
    "washing-machine-repair-service": "Washing Machine Repair",
}
LEGACY_REVIEWS = set(chain(AC_REVIEWS, AC_INSTALLATION_REVIEWS, AC_REMOVAL_REVIEWS, WASHING_REVIEWS))


def workbook_group(service):
    if service.name in SERVICE_REVIEWS:
        return service.name
    return SERVICE_ALIASES.get(service.name) or SLUG_ALIASES.get(service.slug)


def had_legacy_import(service):
    text = f"{service.name} {service.slug}".casefold()
    if re.search(r"washing[\s-]*machine", text):
        return True
    return bool(re.search(r"\bac\b|air[\s-]*condition", text) and not re.search(r"\bcctv\b", text))


class Command(BaseCommand):
    help = "Replace the previous business-supplied review import with workbook reviews; preserve booking and manually added reviews."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show the planned replacement without changing reviews.")

    @transaction.atomic
    def handle(self, *args, **options):
        services = list(Service.objects.all().order_by("slug"))
        legacy_ids = {
            uuid5(NAMESPACE_URL, f"purplesquad:supplied-reviews:2026-10:{service.id}:{name}:{comment}")
            for service in services if had_legacy_import(service)
            for name, comment, _ in LEGACY_REVIEWS
        }
        legacy = Review.objects.filter(id__in=legacy_ids, booking__isnull=True, customer__isnull=True)
        removed = legacy.count()
        targets = [(service, workbook_group(service)) for service in services if service.is_active]
        targets = [(service, group) for service, group in targets if group]
        matched_groups = {group for _, group in targets}
        missing_groups = set(SERVICE_REVIEWS) - matched_groups
        expected = sum(len(SERVICE_REVIEWS[group]) for _, group in targets)

        if options["dry_run"]:
            self.stdout.write(f"Would remove {removed} previous imported reviews and process {expected} workbook reviews across {len(targets)} active services.")
        else:
            legacy.delete()
            created = 0
            for service, group in targets:
                for index, (name, comment, rating) in enumerate(SERVICE_REVIEWS[group], start=1):
                    review_id = uuid5(NAMESPACE_URL, f"purplesquad:workbook-reviews:2026-10:{service.id}:{group}:{index}:{name}:{comment}")
                    _, added = Review.objects.get_or_create(
                        id=review_id,
                        defaults={"service": service, "reviewer_name": name, "comment": comment, "rating": rating, "is_visible": True},
                    )
                    created += int(added)
            self.stdout.write(self.style.SUCCESS(
                f"Removed {removed} previous imported reviews; added {created} of {expected} workbook reviews across {len(targets)} active services. Customer booking and manual reviews were preserved."
            ))
        if missing_groups:
            self.stderr.write("No active service matched workbook groups: " + ", ".join(sorted(missing_groups)))
