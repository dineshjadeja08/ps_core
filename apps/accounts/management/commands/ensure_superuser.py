import os

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User, UserRole
from apps.accounts.validators import normalize_account_phone_number


class Command(BaseCommand):
    help = "Create or update the production superuser from environment variables."

    def handle(self, *args, **options):
        phone_number = os.environ.get("DJANGO_SUPERUSER_PHONE_NUMBER", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip() or None

        if not phone_number:
            raise CommandError("DJANGO_SUPERUSER_PHONE_NUMBER is required.")
        if not password:
            raise CommandError("DJANGO_SUPERUSER_PASSWORD is required.")

        try:
            phone_number = normalize_account_phone_number(phone_number)
        except ValidationError as exc:
            raise CommandError("DJANGO_SUPERUSER_PHONE_NUMBER must be a valid phone number.") from exc

        user = User.objects.filter(phone_number=phone_number).first()
        if user is None and phone_number.startswith("+91"):
            legacy_numbers = (phone_number[3:], phone_number[1:])
            legacy_users = list(
                User.objects.filter(
                    phone_number__in=legacy_numbers,
                    role__in=(UserRole.ADMIN, UserRole.SUPER_ADMIN),
                )
            )
            if len(legacy_users) == 1:
                user = legacy_users[0]
                user.phone_number = phone_number
        created = user is None
        if created:
            user = User(phone_number=phone_number)

        user.email = email
        user.role = UserRole.SUPER_ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_verified = True
        user.is_active = True
        user.set_password(password)
        user.save(
            update_fields=[
                "email",
                "role",
                "is_staff",
                "is_superuser",
                "is_verified",
                "is_active",
                "password",
                "updated_at",
            ]
        )

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} superuser {phone_number}."))
