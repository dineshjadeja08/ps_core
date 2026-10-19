from django.db import migrations, models


APP_CATEGORY_CHOICES = (
    ("water-tank", "Water Tank Cleaning"),
    ("sofa", "Sofa Repair"),
    ("mosquito-net", "Mosquito Net"),
    ("ac", "AC Service"),
    ("washing-machine", "Washing Machine"),
    ("refrigerator", "Refrigerator"),
    ("water-purifier", "Water Purifier"),
    ("tv", "TV Repair"),
    ("geyser", "Geyser"),
    ("microwave", "Microwave"),
    ("dishwasher", "Dishwasher"),
    ("chimney", "Chimney"),
    ("cctv", "CCTV"),
)


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0018_blogpost")]

    operations = [
        migrations.AddField(
            model_name="service",
            name="show_in_app",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Show this service in the mobile app",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="app_category",
            field=models.CharField(
                blank=True,
                choices=APP_CATEGORY_CHOICES,
                default="",
                help_text="Icon group in the mobile app",
                max_length=32,
            ),
        ),
    ]
