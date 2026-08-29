from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


GROUP_PERMISSIONS = {
    "Operations Admin": {
        "accounts": ["view_user", "view_customerprofile"],
        "bookings": ["add_booking", "change_booking", "view_booking", "view_bookingstatushistory"],
        "catalogue": ["view_service", "view_servicecategory"],
        "locations": ["add_address", "change_address", "view_address", "view_servicearea"],
        "notifications": ["change_notification", "view_notification"],
        "operations": ["add_lead", "change_lead", "view_lead", "view_leadstatushistory"],
        "payments": ["view_payment"],
        "technicians": ["change_technicianprofile", "view_technicianprofile"],
    },
    "Customer Support": {
        "accounts": ["view_user", "view_customerprofile"],
        "bookings": ["view_booking"],
        "locations": ["view_address"],
        "notifications": ["change_notification", "view_notification"],
        "operations": ["add_lead", "change_lead", "view_lead", "view_leadstatushistory"],
    },
    "Catalogue Manager": {
        "catalogue": [
            "add_service",
            "change_service",
            "delete_service",
            "view_service",
            "add_servicecategory",
            "change_servicecategory",
            "delete_servicecategory",
            "view_servicecategory",
            "add_serviceimage",
            "change_serviceimage",
            "delete_serviceimage",
            "view_serviceimage",
        ],
        "operations": [
            "add_homepagebanner",
            "change_homepagebanner",
            "delete_homepagebanner",
            "view_homepagebanner",
            "add_faq",
            "change_faq",
            "delete_faq",
            "view_faq",
        ],
    },
    "Finance": {
        "bookings": ["view_booking"],
        "payments": ["view_payment"],
    },
    "Technician Coordinator": {
        "accounts": ["view_user"],
        "bookings": ["change_booking", "view_booking", "view_bookingstatushistory"],
        "technicians": ["change_technicianprofile", "view_technicianprofile"],
    },
}


class Command(BaseCommand):
    help = "Create Purple Squad staff groups and assign baseline Django model permissions."

    def handle(self, *args, **options):
        super_admin, _ = Group.objects.get_or_create(name="Super Admin")
        all_permissions = Permission.objects.all()
        super_admin.permissions.set(all_permissions)
        self.stdout.write(self.style.SUCCESS("Configured Super Admin group."))

        for group_name, app_permissions in GROUP_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            permissions = []
            for app_label, codenames in app_permissions.items():
                permissions.extend(Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames))
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(f"Configured {group_name} group with {len(permissions)} permissions."))
