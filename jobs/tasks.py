from celery import shared_task

from . import publishing, rendering
from .models import Job


@shared_task
def process_job(job_id):
    """Task Celery unico per entrambi i flussi API: rendering, e se il Job
    ha una Destinazione (POST /pubblica) la pubblicazione a seguire — ma
    SOLO se il chiamante ha dato consenso_pubblicazione E la Destinazione
    ha la pubblicazione automatica attiva in questo momento (vedi
    publishing.finestra_automatica_attiva). Postnect resta l'unico
    responsabile della decisione: senza queste due condizioni il Job
    resta 'generato', pronto per la pubblicazione manuale dalla dashboard
    (JobPubblicaView) — mai pubblicato solo perché il chiamante lo chiede.
    Va sempre accodato con .delay()/.apply_async(), mai chiamato in
    request-response diretto."""
    job = Job.objects.select_related('template', 'destinazione').get(pk=job_id)

    rendering.esegui_rendering(job)
    job.refresh_from_db()

    if (
        job.stato == 'generato' and job.destinazione_id and job.consenso_pubblicazione
        and publishing.finestra_automatica_attiva(job.destinazione)
    ):
        publishing.esegui_pubblicazione(job)
        job.refresh_from_db()

    return job.stato
