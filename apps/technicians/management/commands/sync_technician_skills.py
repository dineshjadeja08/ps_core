from django.core.management.base import BaseCommand

from apps.catalogue.models import ServiceCategory
from apps.technicians.models import TechnicianSkill


class Command(BaseCommand):
    help = "Create a technician skill for every active service category so partners can pick services during KYC. Never edits or removes skills."

    def handle(self, *args, **options):
        created = 0
        for name in ServiceCategory.objects.filter(is_active=True).order_by("name").values_list("name", flat=True):
            if not TechnicianSkill.objects.filter(name__iexact=name).exists():
                TechnicianSkill.objects.create(name=name)
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Technician skills created: {created}"))
