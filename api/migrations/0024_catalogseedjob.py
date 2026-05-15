import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0023_userprofile"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CatalogSeedJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("json_file", models.FileField(upload_to="catalog_seed_jobs/%Y/%m/")),
                ("reset_catalog", models.BooleanField(default=True)),
                ("reset_orders", models.BooleanField(default=False)),
                ("total_products", models.PositiveIntegerField(default=0)),
                ("processed_products", models.PositiveIntegerField(default=0)),
                ("created_products", models.PositiveIntegerField(default=0)),
                ("created_categories", models.PositiveIntegerField(default=0)),
                ("created_images", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True, default="")),
                ("item_errors", models.JSONField(blank=True, default=list)),
                ("rq_job_id", models.CharField(blank=True, default="", max_length=128)),
                ("env", models.CharField(blank=True, default="", max_length=32)),
                ("is_local_images", models.BooleanField(default=False)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="catalog_seed_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Catalog seed job",
                "verbose_name_plural": "Catalog seed jobs",
                "ordering": ["-created_at"],
            },
        ),
    ]
