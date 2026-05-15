"""Enqueue catalog seed jobs on Redis (django-rq) with a thread fallback."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def enqueue_catalog_seed_job(job_id: int) -> str | None:
    """
    Queue `run_catalog_seed_job` on Redis. Returns RQ job id, or None when using
    the in-process thread fallback (no Redis).
    """
    from api.seed_catalog_tasks import run_catalog_seed_job

    try:
        import django_rq

        queue = django_rq.get_queue("catalog_seed")
        rq_job = queue.enqueue(
            run_catalog_seed_job,
            job_id,
            job_timeout=3600,
            result_ttl=86400,
            failure_ttl=86400,
        )
        return rq_job.id
    except Exception as exc:
        logger.warning("Redis/RQ unavailable (%s); running seed job %s in background thread", exc, job_id)

    thread = threading.Thread(
        target=run_catalog_seed_job,
        args=(job_id,),
        name=f"catalog-seed-{job_id}",
        daemon=True,
    )
    thread.start()
    return None
