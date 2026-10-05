from django.db import migrations
from django.db.models import F


QUESTION = "Will there be a visiting charge if I don’t avail the service?"
ANSWER = (
    "Yes, a ₹299 visiting charge will apply if you do not proceed with the service "
    "after the technician’s visit."
)


def add_visiting_charge_faq(apps, schema_editor):
    FAQ = apps.get_model("operations", "FAQ")
    Service = apps.get_model("catalogue", "Service")
    alias = schema_editor.connection.alias

    for service_id in Service.objects.using(alias).values_list("id", flat=True).iterator():
        faqs = FAQ.objects.using(alias).filter(service_id=service_id)
        faq = faqs.filter(question=QUESTION).order_by("-is_active", "created_at").first()
        if faq is None or faq.display_order != 5:
            later_faqs = faqs.filter(display_order__gte=5)
            if faq is not None:
                later_faqs = later_faqs.exclude(pk=faq.pk)
            later_faqs.update(display_order=F("display_order") + 1)
        if faq is None:
            FAQ.objects.using(alias).create(
                service_id=service_id,
                question=QUESTION,
                answer=ANSWER,
                display_order=5,
                is_active=True,
            )
        else:
            faqs.filter(pk=faq.pk).update(answer=ANSWER, display_order=5, is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0004_alter_lead_source"),
        ("catalogue", "0015_seed_all_chennai_seo_area_pages"),
    ]

    operations = [migrations.RunPython(add_visiting_charge_faq, migrations.RunPython.noop)]
