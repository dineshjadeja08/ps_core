from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0007_sms_channel")]

    operations = [migrations.AlterField(
        model_name="notification", name="channel",
        field=models.CharField(choices=[("SMS", "SMS"), ("PUSH", "Push"), ("WHATSAPP", "WhatsApp")], max_length=16),
    )]
