from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from common.models import BaseModel


class UserRole(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    TECHNICIAN = "TECHNICIAN", "Technician"
    ADMIN = "ADMIN", "Admin"
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("A phone number is required.")
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.SUPER_ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    username = None
    phone_number = models.CharField(max_length=16, unique=True)
    email = models.EmailField(blank=True, null=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=32, choices=UserRole.choices, default=UserRole.CUSTOMER)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    class Meta:
        indexes = [
            models.Index(fields=["phone_number"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return self.phone_number


class CustomerProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    display_name = models.CharField(max_length=255, blank=True)
    alternate_phone = models.CharField(max_length=16, blank=True)

    def __str__(self):
        return self.display_name or self.user.phone_number


class CustomerSupportNote(BaseModel):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="support_notes")
    note = models.TextField()
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="customer_support_notes_created",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["customer", "created_at"]),
        ]

    def __str__(self):
        return f"Support note for {self.customer.phone_number}"
