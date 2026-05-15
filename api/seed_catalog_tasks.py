"""Background worker entrypoint for catalog seed jobs."""

from django.db import close_old_connections
from django.utils import timezone

from api.models import CatalogSeedJob
from api.seed_catalog import seed_from_products_json


def run_catalog_seed_job(job_id: int) -> None:
    close_old_connections()
    job = CatalogSeedJob.objects.get(pk=job_id)

    if job.status not in (CatalogSeedJob.Status.PENDING, CatalogSeedJob.Status.RUNNING):
        return

    job.status = CatalogSeedJob.Status.RUNNING
    job.started_at = timezone.now()
    job.error_message = ""
    job.save(update_fields=["status", "started_at", "error_message"])

    env = job.env or "local"
    is_local_images = job.is_local_images
    local_root = None
    if is_local_images:
        from django.conf import settings

        local_root = getattr(settings, "SEED_LOCAL_IMAGE_ROOT", None)

    try:
        with job.json_file.open("rb") as uploaded:
            json_bytes = uploaded.read()

        result = seed_from_products_json(
            json_bytes=json_bytes,
            reset_catalog=job.reset_catalog,
            reset_orders=job.reset_orders,
            is_local_images=is_local_images,
            local_image_root=local_root,
            job_id=job_id,
        )

        job.refresh_from_db()
        job.status = CatalogSeedJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.created_products = result.created_products
        job.created_categories = result.created_categories
        job.created_images = result.created_images
        job.processed_products = job.total_products
        job.save(
            update_fields=[
                "status",
                "completed_at",
                "created_products",
                "created_categories",
                "created_images",
                "processed_products",
            ]
        )
    except Exception as exc:
        job.refresh_from_db()
        job.status = CatalogSeedJob.Status.FAILED
        job.completed_at = timezone.now()
        job.error_message = str(exc)
        job.save(update_fields=["status", "completed_at", "error_message"])
        raise
    finally:
        close_old_connections()
