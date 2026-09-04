from celery import shared_task

from . import rendering
from .models import Job


@shared_task
def render_job(job_id):
    """Task Celery: esegue il rendering di un Job (screenshot Playwright).
    Va sempre accodato con .delay()/.apply_async(), mai chiamato in
    request-response diretto."""
    job = Job.objects.select_related('template').get(pk=job_id)
    rendering.esegui_rendering(job)
    return job.stato
