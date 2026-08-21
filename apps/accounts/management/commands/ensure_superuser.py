import os

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User, UserRole


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

        user, created = User.objects.get_or_create(
            phone_number=phone_number,
            defaults={
                "email": email,
                "role": UserRole.SUPER_ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_verified": True,
                "is_active": True,
            },
        )

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
