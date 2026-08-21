# Generated for Purple Squad Phase 2.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("phone_number", models.CharField(max_length=16, unique=True)),
                ("email", models.EmailField(blank=True, max_length=254, null=True)),
                ("first_name", models.CharField(blank=True, max_length=150)),
                ("last_name", models.CharField(blank=True, max_length=150)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("CUSTOMER", "Customer"),
                            ("TECHNICIAN", "Technician"),
                            ("ADMIN", "Admin"),
                            ("SUPER_ADMIN", "Super Admin"),
                        ],
                        default="CUSTOMER",
                        max_length=32,
                    ),
                ),
                ("is_verified", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["phone_number"], name="accounts_us_phone_n_816682_idx"),
                    models.Index(fields=["role"], name="accounts_us_role_d37dd3_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CustomerProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("display_name", models.CharField(blank=True, max_length=255)),
                ("alternate_phone", models.CharField(blank=True, max_length=16)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_profile",
                        to="accounts.user",
                    ),
                ),
            ],
        ),
    ]
