import secrets

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


def _generate_api_key():
    return secrets.token_urlsafe(32)


def _fernet():
    key = getattr(settings, 'MASTER_ENCRYPTION_KEY', '')
    if not key:
        raise RuntimeError(
            'MASTER_ENCRYPTION_KEY non configurata: impossibile cifrare/decifrare '
            'i token delle Destinazioni. Generarla con: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class ApiClient(models.Model):
    """Credenziale per l'autenticazione delle chiamate esterne a Postnect
    (header X-API-Key). client_id deve corrispondere a un cliente esistente
    nell'anagrafica condivisa del Portale (vedi portal_client.py) — Postnect
    non tiene un proprio modello Cliente."""

    client_id = models.UUIDField(help_text='client_id del cliente nell’anagrafica del Portale FBO.')
    api_key = models.CharField(max_length=64, unique=True, default=_generate_api_key, editable=False)
    attivo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'ApiClient {self.client_id}'


class Template(models.Model):
    client_id = models.UUIDField()
    nome = models.CharField(max_length=255)
    html_content = models.TextField(help_text='Markup con placeholder tipo {{risultato}}.')
    css_content = models.TextField(blank=True, null=True)
    campi_richiesti = models.JSONField(
        default=list,
        help_text='Elenco dei placeholder attesi nei dati del Job, es. ["avversario", "risultato", "data"].',
    )
    larghezza = models.PositiveIntegerField(
        default=1200, help_text='Larghezza dello screenshot in pixel. Default 1200x630 (formato Facebook link/foto).',
    )
    altezza = models.PositiveIntegerField(
        default=630, help_text='Altezza dello screenshot in pixel (solo il viewport iniziale: se il contenuto è più alto, lo screenshot lo segue comunque per intero).',
    )
    attivo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome


class Destinazione(models.Model):
    PIATTAFORMA_CHOICES = [
        ('facebook', 'Facebook'),
    ]

    client_id = models.UUIDField()
    piattaforma = models.CharField(max_length=32, choices=PIATTAFORMA_CHOICES, default='facebook')
    page_id = models.CharField(max_length=255)
    access_token_cifrato = models.BinaryField(
        help_text='Access token cifrato con Fernet (MASTER_ENCRYPTION_KEY). Non leggere/scrivere direttamente: usare access_token.',
    )
    nome_descrittivo = models.CharField(max_length=255, help_text='Es. "Pagina FB ASD Calcio Olgiate".')

    # Pubblicazione automatica: di default OGNI pubblicazione è manuale
    # (un operatore la conferma dalla dashboard, vedi JobPubblicaView) anche
    # quando il chiamante (es. Squadfy) ha dato consenso — Postnect resta
    # l'unico responsabile della decisione finale, mai il chiamante. Questi
    # campi permettono di delegare la decisione in automatico solo dentro
    # una finestra giorni/orario esplicita, e solo se consenso_pubblicazione
    # sul Job è True (vedi publishing.finestra_automatica_attiva).
    pubblicazione_automatica = models.BooleanField(
        default=False,
        help_text='Se attivo, i Job con consenso pubblicano da soli (dentro la finestra sotto), senza intervento manuale.',
    )
    automatica_giorni = models.JSONField(
        default=list,
        blank=True,
        help_text='Giorni della settimana in cui è valida la pubblicazione automatica (0=lunedì...6=domenica). Vuoto = tutti i giorni.',
    )
    automatica_ora_inizio = models.TimeField(
        null=True, blank=True, help_text='Inizio della finestra oraria per la pubblicazione automatica. Vuoto = nessun limite iniziale.',
    )
    automatica_ora_fine = models.TimeField(
        null=True, blank=True, help_text='Fine della finestra oraria per la pubblicazione automatica. Vuoto = nessun limite finale.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome_descrittivo

    @property
    def access_token(self):
        return _fernet().decrypt(bytes(self.access_token_cifrato)).decode()

    @access_token.setter
    def access_token(self, value):
        self.access_token_cifrato = _fernet().encrypt(value.encode())


class Job(models.Model):
    STATO_CHOICES = [
        ('in_coda', 'In coda'),
        ('generato', 'Generato'),
        ('pubblicato', 'Pubblicato'),
        ('errore', 'Errore'),
    ]

    client_id = models.UUIDField()
    template = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='job_set')
    dati = models.JSONField(default=dict, help_text='Valori per i placeholder del Template.')
    stato = models.CharField(max_length=16, choices=STATO_CHOICES, default='in_coda')
    immagine_path = models.CharField(max_length=500, blank=True, null=True)
    destinazione = models.ForeignKey(
        Destinazione, on_delete=models.PROTECT, related_name='job_set', blank=True, null=True,
        help_text='Nullo se il job è solo generazione, senza pubblicazione.',
    )
    caption = models.TextField(
        blank=True, null=True,
        help_text='Didascalia da usare in pubblicazione (POST /pubblica). Non usata se destinazione è nullo.',
    )
    consenso_pubblicazione = models.BooleanField(
        default=False,
        help_text='Consenso a pubblicare dato dal chiamante (es. il direttore sportivo via Squadfy). '
                   'Necessario ma non sufficiente per la pubblicazione automatica: serve anche che la '
                   'Destinazione abbia pubblicazione_automatica attiva e si sia dentro la sua finestra '
                   'giorni/orario — altrimenti il Job resta pronto per la pubblicazione manuale.',
    )
    post_id_risultante = models.CharField(max_length=255, blank=True, null=True)
    errore_messaggio = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Job {self.pk} ({self.stato})'
