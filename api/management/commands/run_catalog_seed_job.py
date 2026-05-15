from django.core.management.base import BaseCommand, CommandError

from api.models import CatalogSeedJob
from api.seed_catalog_queue import enqueue_catalog_seed_job
from api.seed_catalog_tasks import run_catalog_seed_job


class Command(BaseCommand):
    help = "Run a catalog seed job synchronously or enqueue pending jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--job-id",
            type=int,
            help="Run a specific CatalogSeedJob by primary key (blocking).",
        )
        parser.add_argument(
            "--enqueue-pending",
            action="store_true",
            help="Enqueue all pending jobs on the catalog_seed RQ queue.",
        )

    def handle(self, *args, **options):
        job_id = options.get("job_id")
        enqueue_pending = options.get("enqueue_pending")

        if job_id:
            if not CatalogSeedJob.objects.filter(pk=job_id).exists():
                raise CommandError(f"CatalogSeedJob #{job_id} does not exist.")
            self.stdout.write(f"Running seed job #{job_id} synchronously...")
            run_catalog_seed_job(job_id)
            job = CatalogSeedJob.objects.get(pk=job_id)
            self.stdout.write(self.style.SUCCESS(f"Job #{job_id} finished: {job.status}"))
            return

        if enqueue_pending:
            pending = CatalogSeedJob.objects.filter(status=CatalogSeedJob.Status.PENDING)
            count = 0
            for job in pending:
                rq_id = enqueue_catalog_seed_job(job.pk)
                if rq_id:
                    job.rq_job_id = rq_id
                    job.save(update_fields=["rq_job_id"])
                count += 1
            self.stdout.write(self.style.SUCCESS(f"Enqueued {count} pending job(s)."))
            return

        raise CommandError("Pass --job-id=<id> or --enqueue-pending.")
