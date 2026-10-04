from django.db import migrations

from apps.catalogue.seo_keywords import keyword_targets


def populate_keyword_targets(apps, schema_editor):
    SeoLandingPage = apps.get_model("catalogue", "SeoLandingPage")

    for page in SeoLandingPage.objects.all().iterator():
        location = page.area or page.city
        targets = keyword_targets(page.service_slug, location, page.service_name)
        SeoLandingPage.objects.filter(pk=page.pk).update(
            **targets,
            content_status="READY" if page.is_indexable else "NEEDS_REVIEW",
        )


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0016_add_seo_keyword_targeting")]

    operations = [migrations.RunPython(populate_keyword_targets, migrations.RunPython.noop)]
