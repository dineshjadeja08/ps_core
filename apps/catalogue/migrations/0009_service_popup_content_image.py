from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0008_service_presentation_images")]

    operations = [
        migrations.AddField(
            model_name="service",
            name="popup_content_image",
            field=models.ImageField(blank=True, upload_to="services/popup-content/"),
        ),
    ]
