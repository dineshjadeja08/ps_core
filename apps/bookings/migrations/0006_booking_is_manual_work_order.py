from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bookings", "0005_booking_contact_phone")]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="is_manual_work_order",
            field=models.BooleanField(default=False),
        ),
    ]
