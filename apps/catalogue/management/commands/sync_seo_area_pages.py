from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalogue.models import SeoLandingPage
from apps.catalogue.seo_keywords import keyword_targets
from apps.locations.service_area_data import CHENNAI_LOCALITIES


class Command(BaseCommand):
    help = "Create missing Chennai area pages for every configured SEO service family."

    def handle(self, *args, **options):
        parents = SeoLandingPage.objects.filter(city__iexact="Chennai", area_slug="", is_active=True)
        created_count = 0
        updated_count = 0

        for parent in parents:
            for area, postal_code in CHENNAI_LOCALITIES:
                area_slug = slugify(area)
                page, created = SeoLandingPage.objects.get_or_create(
                    service_slug=parent.service_slug,
                    area_slug=area_slug,
                    defaults=self._defaults(parent, area, postal_code),
                )
                if created:
                    created_count += 1
                elif page.postal_code != postal_code:
                    page.postal_code = postal_code
                    page.save(update_fields=("postal_code", "page_type", "page_slug", "updated_at"))
                    updated_count += 1
                keyword_values = keyword_targets(parent.service_slug, area, parent.service_name)
                missing_keyword_fields = []
                for field, value in keyword_values.items():
                    if not getattr(page, field):
                        setattr(page, field, value)
                        missing_keyword_fields.append(field)
                if missing_keyword_fields:
                    page.save(update_fields=(*missing_keyword_fields, "page_type", "page_slug", "updated_at"))
                page.featured_services.set(parent.featured_services.all())

        self.stdout.write(
            self.style.SUCCESS(
                f"SEO area pages synced: {created_count} created, {updated_count} PIN codes updated."
            )
        )

    @staticmethod
    def _defaults(parent, area, postal_code):
        service_name = parent.service_name
        return {
            "service_name": service_name,
            "category_slug": parent.category_slug,
            "city": parent.city,
            "area": area,
            "postal_code": postal_code,
            "page_slug": f"{parent.service_slug}/{slugify(area)}",
            "meta_title": f"{service_name} in {area}, Chennai | Purple Squad",
            "meta_description": (
                f"Book {service_name.lower()} in {area}, Chennai {postal_code}. "
                "Check live services, pricing and address availability with Purple Squad."
            ),
            "h1": f"{service_name} in {area}, Chennai",
            "intro_content": (
                f"Purple Squad provides {service_name.lower()} for supported addresses in {area}, "
                f"Chennai {postal_code}. Choose a service, review the current catalogue price and "
                "confirm availability for your exact address before booking."
            ),
            "pricing_intro": parent.pricing_intro,
            "coverage_areas": [area],
            "faqs": [
                {
                    "question": f"Is {service_name.lower()} available in {area}?",
                    "answer": (
                        f"Purple Squad serves supported addresses in PIN code {postal_code}. "
                        "Enter the exact service address during booking to confirm availability."
                    ),
                },
                {
                    "question": "Can I see the price before booking?",
                    "answer": "Yes. Current catalogue pricing is shown before you continue to booking.",
                },
            ],
            "is_active": True,
            "is_indexable": False,
            **keyword_targets(parent.service_slug, area, service_name),
        }
