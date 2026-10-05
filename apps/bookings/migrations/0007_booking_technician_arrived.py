from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bookings", "0006_booking_is_manual_work_order")]

    operations = [
        migrations.AlterField(
            model_name="booking",
            name="booking_status",
            field=models.CharField(
                choices=[
                    ("PENDING_PAYMENT", "Pending payment"), ("PAYMENT_FAILED", "Payment failed"),
                    ("CONFIRMED", "Confirmed"), ("TECHNICIAN_ASSIGNED", "Technician assigned"),
                    ("TECHNICIAN_EN_ROUTE", "Technician en route"), ("TECHNICIAN_ARRIVED", "Technician arrived"),
                    ("IN_PROGRESS", "In progress"), ("COMPLETED", "Completed"), ("CLOSED", "Closed"),
                    ("CANCELLED", "Cancelled"), ("REFUND_PENDING", "Refund pending"), ("REFUNDED", "Refunded"),
                ],
                default="PENDING_PAYMENT", max_length=32,
            ),
        ),
    ]
