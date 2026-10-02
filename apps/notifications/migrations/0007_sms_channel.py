from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0006_push_only_channel")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="channel",
            field=models.CharField(choices=[("SMS", "SMS"), ("PUSH", "Push")], max_length=16),
        ),
    ]
