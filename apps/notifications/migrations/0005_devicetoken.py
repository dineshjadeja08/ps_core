import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("notifications", "0004_alter_notification_event_alter_notification_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeviceToken",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token", models.TextField(unique=True)),
                ("platform", models.CharField(choices=[("WEB", "Web"), ("ANDROID", "Android"), ("IOS", "iOS")], default="WEB", max_length=16)),
                ("is_active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="device_tokens", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="devicetoken",
            index=models.Index(fields=["user", "is_active"], name="notificatio_user_id_f0e72c_idx"),
        ),
    ]
