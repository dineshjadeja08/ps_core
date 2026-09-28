from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0005_devicetoken")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="channel",
            field=models.CharField(choices=[("PUSH", "Push")], max_length=16),
        ),
    ]
