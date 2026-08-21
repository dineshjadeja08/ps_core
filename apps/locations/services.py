from django.db import transaction

from apps.locations.models import Address, ServiceArea, normalize_postal_code


def get_active_service_area(postal_code):
    normalized = normalize_postal_code(postal_code)
    return ServiceArea.objects.filter(postal_code=normalized, is_active=True).first()


@transaction.atomic
def enforce_single_default(address):
    if not address.is_default:
        return address
    Address.objects.filter(customer=address.customer, is_default=True).exclude(pk=address.pk).update(
        is_default=False
    )
    return address
