from django.db import migrations
from django.utils import timezone


ADMIN_PHONE_NUMBER = "+916362365344"


def promote_admin(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(phone_number=ADMIN_PHONE_NUMBER).update(
        role="ADMIN",
        is_staff=True,
        is_verified=True,
        is_active=True,
        updated_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_adminmfachallenge"),
    ]

    operations = [
        migrations.RunPython(promote_admin, migrations.RunPython.noop),
    ]
