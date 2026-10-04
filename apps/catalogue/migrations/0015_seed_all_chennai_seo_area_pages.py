from django.db import migrations


def seed_area_pages(apps, schema_editor):
    SeoLandingPage = apps.get_model("catalogue", "SeoLandingPage")
    Service = apps.get_model("catalogue", "Service")
    ServiceAreaLocality = apps.get_model("locations", "ServiceAreaLocality")

    water_parent = SeoLandingPage.objects.filter(
        service_slug="water-purifier-service-chennai", area_slug=""
    ).first()
    if water_parent:
        water_services = Service.objects.filter(slug="water-purifier-repair-services")
        water_parent.featured_services.set(water_services)

    parents = SeoLandingPage.objects.filter(city__iexact="Chennai", area_slug="", is_active=True)
    localities = ServiceAreaLocality.objects.select_related("service_area").filter(
        service_area__city__iexact="Chennai",
        service_area__is_active=True,
        is_active=True,
    )

    for parent in parents:
        for locality in localities:
            area = locality.name
            area_slug = locality.slug
            postal_code = locality.service_area.postal_code
            defaults = {
                "service_name": parent.service_name,
                "category_slug": parent.category_slug,
                "city": parent.city,
                "area": area,
                "postal_code": postal_code,
                "page_slug": f"{parent.service_slug}/{area_slug}",
                "page_type": "SERVICE_AREA",
                "meta_title": f"{parent.service_name} in {area}, Chennai | Purple Squad",
                "meta_description": (
                    f"Book {parent.service_name.lower()} in {area}, Chennai {postal_code}. "
                    "Check live services, pricing and address availability with Purple Squad."
                ),
                "h1": f"{parent.service_name} in {area}, Chennai",
                "intro_content": (
                    f"Purple Squad provides {parent.service_name.lower()} for supported addresses in {area}, "
                    f"Chennai {postal_code}. Choose a service, review the current catalogue price and "
                    "confirm availability for your exact address before booking."
                ),
                "pricing_intro": parent.pricing_intro,
                "coverage_areas": [area],
                "faqs": [
                    {
                        "question": f"Is {parent.service_name.lower()} available in {area}?",
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
                "include_in_sitemap": True,
            }
            page, created = SeoLandingPage.objects.get_or_create(
                service_slug=parent.service_slug,
                area_slug=area_slug,
                defaults=defaults,
            )
            if not created:
                update_fields = []
                for field, value in (("postal_code", postal_code), ("page_type", "SERVICE_AREA")):
                    if getattr(page, field) != value:
                        setattr(page, field, value)
                        update_fields.append(field)
                if update_fields:
                    page.save(update_fields=update_fields)
            page.featured_services.set(parent.featured_services.all())


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0014_add_seo_featured_services"),
        ("locations", "0005_seed_service_area_localities"),
    ]

    operations = [migrations.RunPython(seed_area_pages, migrations.RunPython.noop)]
