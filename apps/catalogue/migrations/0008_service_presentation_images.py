from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0007_map_populated_core_catalogue"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="landing_thumbnail",
            field=models.ImageField(blank=True, upload_to="services/landing-thumbnails/"),
        ),
        migrations.AddField(
            model_name="service",
            name="popup_cover_image",
            field=models.ImageField(blank=True, upload_to="services/popup-covers/"),
        ),
        migrations.AddField(
            model_name="service",
            name="list_image",
            field=models.ImageField(blank=True, upload_to="services/list-images/"),
        ),
    ]
