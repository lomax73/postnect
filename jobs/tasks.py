from celery import shared_task

from . import publishing, rendering
from .models import Job


@shared_task
def process_job(job_id):
    """Task Celery unico per entrambi i flussi API: rendering, e se il Job
    ha una Destinazione (POST /pubblica) anche la pubblicazione a seguire.
    Va sempre accodato con .delay()/.apply_async(), mai chiamato in
    request-response diretto."""
    job = Job.objects.select_related('template', 'destinazione').get(pk=job_id)

    rendering.esegui_rendering(job)
    job.refresh_from_db()

    if job.stato == 'generato' and job.destinazione_id:
        publishing.esegui_pubblicazione(job)
        job.refresh_from_db()

    return job.stato
