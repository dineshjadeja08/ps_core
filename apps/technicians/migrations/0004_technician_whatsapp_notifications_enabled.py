from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("technicians", "0003_technicianleave_review_note")]

    operations = [migrations.AddField(
        model_name="technicianprofile", name="whatsapp_notifications_enabled",
        field=models.BooleanField(default=False),
    )]
