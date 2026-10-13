import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0017_populate_seo_keyword_targets")]

    operations = [
        migrations.CreateModel(
            name="BlogPost",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=220)),
                ("slug", models.SlugField(max_length=240, unique=True)),
                ("excerpt", models.CharField(max_length=320)),
                ("body", models.TextField(help_text="Plain text. Start a line with ## for a section heading.")),
                ("author_name", models.CharField(default="Purple Squad Team", max_length=120)),
                ("cover_image_url", models.URLField(blank=True)),
                ("is_published", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("related_service", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="blog_posts", to="catalogue.service")),
            ],
            options={"ordering": ("-published_at", "-created_at")},
        ),
        migrations.AddIndex(
            model_name="blogpost",
            index=models.Index(fields=["is_published", "published_at"], name="catalogue_b_is_publ_1eb1c9_idx"),
        ),
    ]
