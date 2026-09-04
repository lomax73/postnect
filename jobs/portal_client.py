"""Client per l'anagrafica clienti condivisa, esposta dal Portale FBO
(clienti/api/internal/). Postnect non ha un modello Cliente locale: salva
solo il client_id (UUID) e risolve nome/dati chiamando questa API in tempo
reale — nessuna FK cross-database (stesso pattern di FBOPreventivi, vedi
struttura_app_fbo.md).
"""

import ssl

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter

TIMEOUT = 5


class PortalUnavailableError(Exception):
    """Il Portale non ha risposto correttamente (giù, token sbagliato,
    non configurato)."""


class _PinnedCertAdapter(HTTPAdapter):
    """Il certificato self-signed del Portale non ha un campo SAN (solo CN,
    generato con `openssl req -x509 -subj "/CN=..."`): i client TLS moderni
    richiedono SAN e rifiutano la verifica dell'hostname a prescindere da
    quale hostname/IP venga dichiarato. Verifichiamo invece l'identità del
    certificato stesso (pinning): la connessione riesce solo con la chiave
    privata di QUEL certificato esatto — stessa protezione da MITM di una
    verifica normale, senza controllo hostname (qui comunque poco
    significativo: si connette sempre a 127.0.0.1 per la regola Nginx
    `allow 127.0.0.1`, mentre il certificato è per l'IP pubblico del VPS)."""

    def __init__(self, ca_cert_path, **kwargs):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=ca_cert_path)
        self._ssl_context = context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self._ssl_context
        # urllib3 fa una propria verifica dell'hostname (via `assert_hostname`),
        # indipendente da `ssl_context.check_hostname`: va disattivata anche
        # questa, altrimenti richiede comunque un SAN che il certificato non ha.
        kwargs['assert_hostname'] = False
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs['ssl_context'] = self._ssl_context
        kwargs['assert_hostname'] = False
        return super().proxy_manager_for(*args, **kwargs)


def _session():
    session = requests.Session()
    if settings.PORTAL_INTERNAL_CA_CERT:
        session.mount('https://', _PinnedCertAdapter(settings.PORTAL_INTERNAL_CA_CERT))
    return session


def _base_url():
    base = getattr(settings, 'PORTAL_INTERNAL_BASE_URL', '')
    if not base:
        raise PortalUnavailableError('PORTAL_INTERNAL_BASE_URL non configurato.')
    return base.rstrip('/') + '/api/internal/clienti/'


def _headers():
    return {'Authorization': f'Token {settings.PORTAL_API_TOKEN}'}


def list_clienti():
    """Tutti i clienti dell'anagrafica condivisa, come lista di dict."""
    try:
        resp = _session().get(_base_url(), headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise PortalUnavailableError(str(exc)) from exc
    if resp.status_code != 200:
        raise PortalUnavailableError(f'HTTP {resp.status_code}: {resp.text[:200]}')
    return resp.json().get('clienti', [])


def get_cliente(cliente_id):
    """Un cliente per id, o None se non esiste più nell'anagrafica."""
    try:
        resp = _session().get(f'{_base_url()}{cliente_id}/', headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise PortalUnavailableError(str(exc)) from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise PortalUnavailableError(f'HTTP {resp.status_code}: {resp.text[:200]}')
    return resp.json()
