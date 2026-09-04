"""Modulo di pubblicazione sui social. Interfaccia astratta SocialPublisher
+ implementazioni concrete per piattaforma, così da poter aggiungere
InstagramPublisher in futuro senza toccare il resto del sistema (task
Celery, viste API)."""

from abc import ABC, abstractmethod
from pathlib import Path

import requests
from django.conf import settings

GRAPH_API_BASE = 'https://graph.facebook.com'
TIMEOUT = 30


class PublishError(Exception):
    """La pubblicazione sulla piattaforma social è fallita (errore HTTP,
    risposta inattesa, credenziali non valide...)."""


class SocialPublisher(ABC):
    @abstractmethod
    def pubblica(self, immagine_path, caption, destinazione):
        """Pubblica `immagine_path` (Path/str su disco) con `caption` sulla
        `destinazione` (jobs.models.Destinazione) e ritorna il post_id
        risultante. Solleva PublishError in caso di fallimento."""


class FacebookPublisher(SocialPublisher):
    def pubblica(self, immagine_path, caption, destinazione):
        url = f'{GRAPH_API_BASE}/{destinazione.page_id}/photos'
        try:
            with open(immagine_path, 'rb') as immagine:
                resp = requests.post(
                    url,
                    data={'caption': caption or '', 'access_token': destinazione.access_token},
                    files={'source': immagine},
                    timeout=TIMEOUT,
                )
        except requests.RequestException as exc:
            raise PublishError(f'Errore di rete verso la Graph API: {exc}') from exc

        if resp.status_code != 200:
            raise PublishError(f'Graph API HTTP {resp.status_code}: {resp.text[:300]}')

        payload = resp.json()
        post_id = payload.get('post_id') or payload.get('id')
        if not post_id:
            raise PublishError(f'Risposta Graph API senza id: {payload}')
        return post_id


PUBLISHERS = {
    'facebook': FacebookPublisher,
}


def esegui_pubblicazione(job):
    """Pubblica un Job già renderizzato sulla sua Destinazione. Come
    rendering.esegui_rendering, non solleva eccezioni verso il chiamante:
    qualunque errore viene scritto sul Job (stato='errore')."""
    if job.stato != 'generato':
        job.stato = 'errore'
        job.errore_messaggio = f'Impossibile pubblicare: il Job è in stato "{job.stato}", non "generato".'
        job.save(update_fields=['stato', 'errore_messaggio', 'updated_at'])
        return

    destinazione = job.destinazione
    if destinazione is None:
        job.stato = 'errore'
        job.errore_messaggio = 'Impossibile pubblicare: il Job non ha una Destinazione.'
        job.save(update_fields=['stato', 'errore_messaggio', 'updated_at'])
        return

    publisher_cls = PUBLISHERS.get(destinazione.piattaforma)
    if publisher_cls is None:
        job.stato = 'errore'
        job.errore_messaggio = f'Piattaforma non supportata: {destinazione.piattaforma}.'
        job.save(update_fields=['stato', 'errore_messaggio', 'updated_at'])
        return

    immagine_path = Path(settings.MEDIA_ROOT) / job.immagine_path

    try:
        post_id = publisher_cls().pubblica(immagine_path, job.caption, destinazione)
    except PublishError as exc:
        job.stato = 'errore'
        job.errore_messaggio = f'Errore durante la pubblicazione: {exc}'
        job.save(update_fields=['stato', 'errore_messaggio', 'updated_at'])
        return

    job.post_id_risultante = post_id
    job.stato = 'pubblicato'
    job.save(update_fields=['post_id_risultante', 'stato', 'updated_at'])
