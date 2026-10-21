from django.db import migrations


BLOG_FIXES = {
    "ac-unstallation-guide-how-to-remove-a-split-ac-safty-before-moving-home": {
        "slug": "ac-uninstallation-guide-how-to-remove-a-split-ac-safely-before-moving-home",
        "title": "AC Uninstallation Guide: Remove a Split AC Safely",
    },
    "ac-gas-refill-signs-your-ac-has-low-gas-and-what-customers-should-known": {
        "slug": "ac-gas-refill-signs-your-ac-has-low-gas-and-what-customers-should-know",
        "title": "AC Gas Refill: Low-Gas Signs Customers Should Know",
    },
    "ac-chemical-wash-what-it-includes-benefits-and-when-our-ac-need-one": {
        "slug": "ac-chemical-wash-what-it-includes-benefits-and-when-your-ac-needs-one",
        "title": "AC Chemical Wash: Benefits and When Your AC Needs One",
    },
    "washing-machine-water-not-spinning-common-causes-and-simple-checks-before-booking-rrepair": {
        "slug": "washing-machine-not-spinning-common-causes-and-simple-checks-before-booking-a-repair",
        "title": "Washing Machine Not Spinning? Causes and Checks",
    },
}

SERVICE_NAME_FIXES = {
    "general-ac-service": "General AC Service",
    "foam-jet-ac-service": "Foam Jet AC Service",
}


def fix_public_copy(apps, schema_editor):
    BlogPost = apps.get_model("catalogue", "BlogPost")
    Service = apps.get_model("catalogue", "Service")

    for old_slug, values in BLOG_FIXES.items():
        BlogPost.objects.filter(slug=old_slug).update(**values)

    BlogPost.objects.filter(
        slug="ac-installation-checklist-what-to-check-before-and-after-split-ac-installation"
    ).update(title="AC Installation Checklist: Before and After Setup")

    for post in BlogPost.objects.filter(body__contains="2.Does").iterator():
        post.body = post.body.replace("2.Does", "2. Does")
        post.save(update_fields=["body", "updated_at"])

    for slug, name in SERVICE_NAME_FIXES.items():
        Service.objects.filter(slug=slug).update(name=name)


def reverse_public_copy(apps, schema_editor):
    BlogPost = apps.get_model("catalogue", "BlogPost")
    Service = apps.get_model("catalogue", "Service")

    reverse_titles = {
        "ac-uninstallation-guide-how-to-remove-a-split-ac-safely-before-moving-home": (
            "ac-unstallation-guide-how-to-remove-a-split-ac-safty-before-moving-home",
            "AC Unstallation Guide: How to Remove a Split AC Safty Before Moving Home",
        ),
        "ac-gas-refill-signs-your-ac-has-low-gas-and-what-customers-should-know": (
            "ac-gas-refill-signs-your-ac-has-low-gas-and-what-customers-should-known",
            "AC Gas Refill: signs your Ac Has low gas and what customers should known",
        ),
        "ac-chemical-wash-what-it-includes-benefits-and-when-your-ac-needs-one": (
            "ac-chemical-wash-what-it-includes-benefits-and-when-our-ac-need-one",
            "AC Chemical Wash :What it includes,Benefits, and when our AC need one",
        ),
        "washing-machine-not-spinning-common-causes-and-simple-checks-before-booking-a-repair": (
            "washing-machine-water-not-spinning-common-causes-and-simple-checks-before-booking-rrepair",
            "Washing Machine Water Not Spinning? Common Causes and Simple Checks Before Booking Rrepair",
        ),
    }
    for new_slug, (old_slug, old_title) in reverse_titles.items():
        BlogPost.objects.filter(slug=new_slug).update(slug=old_slug, title=old_title)

    BlogPost.objects.filter(
        slug="ac-installation-checklist-what-to-check-before-and-after-split-ac-installation"
    ).update(title="AC Installation Checklist : What to check before and after split AC Installation")
    Service.objects.filter(slug="general-ac-service").update(name="General Ac Service")
    Service.objects.filter(slug="foam-jet-ac-service").update(name="Foam Jet Ac Service")


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0020_seed_mobile_app_service_fields")]

    operations = [migrations.RunPython(fix_public_copy, reverse_public_copy)]
