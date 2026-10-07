import re
from uuid import NAMESPACE_URL, uuid5

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalogue.models import Service
from apps.reviews.models import Review
from apps.reviews.supplied_reviews import AC_INSTALLATION_REVIEWS, AC_REMOVAL_REVIEWS, AC_REVIEWS, WASHING_REVIEWS


class Command(BaseCommand):
    help = "Import five business-supplied reviews per active AC and washing-machine service, without changing existing reviews."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        matched = 0
        ac_index = 0
        for service in Service.objects.filter(is_active=True).order_by("slug"):
            text = f"{service.name} {service.slug}".casefold()
            if re.search(r"washing[\s-]*machine", text):
                reviews = WASHING_REVIEWS
            elif re.search(r"\bac\b|air[\s-]*condition", text) and not re.search(r"\bcctv\b", text):
                if "uninstall" in text or "removal" in text:
                    reviews = AC_REMOVAL_REVIEWS
                elif "install" in text:
                    reviews = AC_INSTALLATION_REVIEWS
                else:
                    reviews = [AC_REVIEWS[(ac_index * 5 + offset) % len(AC_REVIEWS)] for offset in range(5)]
                    ac_index += 1
            else:
                continue
            matched += 1
            for name, comment, rating in reviews:
                review_id = uuid5(NAMESPACE_URL, f"purplesquad:supplied-reviews:2026-10:{service.id}:{name}:{comment}")
                _, added = Review.objects.get_or_create(
                    id=review_id,
                    defaults={"service": service, "reviewer_name": name, "comment": comment, "rating": rating, "is_visible": True},
                )
                created += int(added)
        self.stdout.write(self.style.SUCCESS(f"Imported {created} reviews across {matched} services. Existing reviews and moderation were preserved."))
