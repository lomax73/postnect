# Struttura standard di un'app della famiglia FBO

Riferimento tecnico ricavato analizzando le app già in produzione sul VPS
(FBOPortal, FBOMailer, FBOPreventivi, FBOLeads, FBOAIGate, FBONetVault,
FBORackReport, FBOFiberReport, MKRemote, Squadfy). Usalo come punto di
partenza per qualunque nuova app della famiglia, invece di reinventare lo
stack o le convenzioni ogni volta.

---

## Stack tecnico

- **Framework**: Django (`<6.0` o `>=5.x,<6.0` a seconda dell'app — fissare
  sempre un range, mai versione libera).
- **Database**: SQLite in produzione per la quasi totalità delle app
  (`db.sqlite3` nella root del progetto). Postgres è usato solo se serve
  davvero concorrenza/volume alto (es. FBOAIGate lo supporta via
  `DB_ENGINE=postgresql`, ma di default resta comunque su sqlite).
- **Coda asincrona**: Celery + Redis, solo se il progetto ha lavoro di
  background reale (invio email, generazione documenti, rendering). Redis è
  **condiviso** su un'unica istanza del VPS: ogni app usa un **numero di
  database Redis diverso** per non collidere in coda né nei channel layer.
  Allocazione nota finora:
  - `0` — MKRemote (Celery)
  - `1` — MKRemote (Channels/WebSocket)
  - `2` — FBOMailer (Celery)
  - successivo libero noto: **`3`** — verificare comunque sul VPS prima di
    assegnarlo a una nuova app (`redis-cli -n N ping` / controllare gli
    `.env` di tutte le app deployate), la lista qui può non essere aggiornata.
- **Server applicativo**: `gunicorn` (WSGI) dietro Nginx, oppure `daphne` se
  serve ASGI/WebSocket (channels, come FBOAIGate/MKRemote).
- **Niente Docker**: tutte le app girano da venv nativo + systemd + Nginx
  sullo stesso VPS. Non introdurre Docker per una singola app: rompe il
  modello di deploy uniforme (git pull, restart systemd) usato per tutte le
  altre.

## Struttura del progetto

Layout tipico (Django multi-app):

```
<nomeapp>/
├── <nomeapp>/            # progetto Django: settings.py, urls.py, wsgi.py, asgi.py, (celery.py se serve)
├── accounts/              # API interna di gestione utenti per il Portale (vedi sotto)
├── <dominio1>/            # app di dominio (es. "preventivi/", "invii/", "leads/")
├── <dominio2>/
├── deploy/                # config di deploy (vedi sezione dedicata)
├── static/ , staticfiles/, media/
├── templates/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── REDFLAG_REPORT.md      # report sessioni della skill "redflag"
└── venv/                  # non versionato
```

Pacchetti comuni in `requirements.txt` (aggiungere solo quelli che servono
davvero, non copiare tutto):
```
Django<6.0
python-dotenv
gunicorn
requests
cryptography        # se c'è cifratura Fernet
celery               # se c'è coda async
redis
Pillow                # se si manipolano immagini
psycopg2-binary       # solo se Postgres
channels / channels-redis / daphne   # solo se serve WebSocket/ASGI
```

## `settings.py` — pattern comune

```python
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-...')
DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() == 'true'
ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]
```

**Attenzione**: `.env.example` porta sempre `DJANGO_DEBUG=true` come default
comodo per lo sviluppo locale — in produzione va **sempre** rimesso a
`false` esplicitamente nel `.env` reale, altrimenti qualunque eccezione
espone dati sensibili (incluse chiavi di cifratura) nella pagina di debug di
Django. È un punto su cui più `deploy/README.md` insistono esplicitamente.

## Cifratura a riposo (token/credenziali)

Fernet (`cryptography`), chiave letta da env, **mai hardcoded**. Nome della
variabile d'ambiente **sempre lo stesso** in tutte le app: `MASTER_ENCRYPTION_KEY`.

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Usato da FBOMailer (credenziali SMTP) e FBOLeads (token di ingest); stesso
schema da riusare per qualunque credenziale sensibile in una nuova app.

## Integrazione con il Portale FBO

Il **Portale** (`FBOPortal`) è l'hub centrale: elenca le app come card
cliccabili (modello `AppLink`, app `catalog`) ed espone due API interne,
raggiungibili **solo da `127.0.0.1`** (regola Nginx dedicata, mai esposte
pubblicamente):

### 1. Anagrafica clienti condivisa (il Portale è il server)

Le app satellite **non hanno un modello `Cliente` locale**: salvano solo
`client_id` (UUID) e risolvono nome/dati in tempo reale chiamando
`GET {PORTAL_INTERNAL_BASE_URL}/api/internal/clienti/` (lista) o
`.../clienti/<uuid>/` (dettaglio), header `Authorization: Token
{PORTAL_API_TOKEN}`. Nessuna FK cross-database. Pattern di riferimento:
`FBOPreventivi/preventivi/portal_client.py` — copiare/adattare quel file,
non riscriverlo da zero. Include:
- gestione errori con eccezione dedicata (`PortalUnavailableError`);
- timeout breve (5s);
- verifica TLS del certificato self-signed del Portale via **pinning**
  (`PORTAL_INTERNAL_CA_CERT`), perché il certificato non ha un campo SAN e i
  client TLS moderni altrimenti rifiuterebbero la verifica dell'hostname a
  prescindere.

Env richieste nell'app satellite:
```
PORTAL_INTERNAL_BASE_URL=   # URL loopback del Portale, es. https://127.0.0.1:8443 — MAI l'URL pubblico
PORTAL_API_TOKEN=            # stesso valore di INTERNAL_API_TOKEN nel .env del Portale
PORTAL_PUBLIC_URL=           # solo per link "torna al Portale" in UI, opzionale
PORTAL_INTERNAL_CA_CERT=     # path del certificato self-signed del Portale, vuoto in locale
```

### 2. Gestione utenti (l'app satellite è il server, il Portale è il client)

Ogni app espone un'app `accounts/` con endpoint interni (`InternalUserListView`,
`InternalUserDetailView` in `accounts/views.py`) che il Portale chiama per
creare/modificare/eliminare account Django sull'app satellite da remoto.
Protezione: header `Authorization: Token {INTERNAL_API_TOKEN}`, verificato
contro `settings.INTERNAL_API_TOKEN`, endpoint comunque raggiungibile solo
da `127.0.0.1` via regola Nginx.

Env richiesta nell'app satellite:
```
INTERNAL_API_TOKEN=   # generare con: python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Deploy — pattern identico per ogni app

Utente di sistema dedicato, venv proprio, sottodominio proprio, repo
separato. Provisioning iniziale tipo:

```bash
adduser --system --group --home /opt/<nomeapp> <nomeapp>
mkdir -p /opt/<nomeapp>/app
chown <nomeapp>:<nomeapp> /opt/<nomeapp>/app

sudo -u <nomeapp> git clone <url-repo> /opt/<nomeapp>/app
cd /opt/<nomeapp>/app
sudo -u <nomeapp> python3 -m venv venv
sudo -u <nomeapp> venv/bin/pip install -r requirements.txt

cp .env.example .env   # valorizzare tutto, DJANGO_DEBUG=false
sudo -u <nomeapp> venv/bin/python manage.py migrate
sudo -u <nomeapp> venv/bin/python manage.py collectstatic --noinput
sudo -u <nomeapp> venv/bin/python manage.py createsuperuser

cp deploy/<nomeapp>-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now <nomeapp>-web.service

cp deploy/nginx-<nomeapp>.conf /etc/nginx/sites-available/<nomeapp>
ln -s /etc/nginx/sites-available/<nomeapp> /etc/nginx/sites-enabled/<nomeapp>
nginx -t && systemctl reload nginx
# + certbot --nginx -d <nomeapp>.fbosolution.it (quando c'è un dominio vero)
```

### systemd unit (`deploy/<nomeapp>-web.service`)

```ini
[Unit]
Description=<NomeApp> - Gunicorn
After=network.target

[Service]
Type=simple
User=<nomeapp>
Group=<nomeapp>
WorkingDirectory=/opt/<nomeapp>/app
ExecStart=/opt/<nomeapp>/app/venv/bin/gunicorn <nomeapp>.wsgi:application \
    --bind unix:/run/<nomeapp>/gunicorn.sock \
    --workers 2
RuntimeDirectory=<nomeapp>
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Se c'è Celery, aggiungere una seconda unit `<nomeapp>-worker.service` con
`ExecStart=.../venv/bin/celery -A <nomeapp> worker -l info`.

### Nginx — due file per app, in `deploy/`

1. **`nginx-<nomeapp>-ip-provisional.conf`**: finché non c'è un dominio DNS
   vero, l'app viene servita sull'IP nudo del VPS (`94.177.161.127`) su una
   **porta dedicata**, certificato self-signed proprio in
   `/etc/ssl/<nomeapp>/`. **Ogni app deve avere una porta propria**, mai
   condividerla con altre — porte già occupate per il blocco `/api/internal/`
   (loopback-only): `8443` Portal, `8444` FiberReport, `8445` Preventivi,
   `8446` RackReport, `8447` NetVault, `8449` MKRemote, `8451` FBOLeads,
   `8452` FBOAIGate → prossima libera nota **`8453`**, verificare comunque
   sul VPS prima di usarla. Motivo: sulla porta condivisa 443 il routing
   nginx si basa su `server_name`/header `Host`, e una chiamata interna verso
   `127.0.0.1` senza SNI/Host corretto finisce sul vhost sbagliato (vedi
   `FBOPortal/REDFLAG_REPORT.md`, sessione 2026-08-08, causa di un bug reale
   già capitato).
2. **`nginx-<nomeapp>.conf`**: il template "finale" a sottodominio
   (`<nomeapp>.fbosolution.it`), da attivare quando il dominio è pronto.

Entrambi seguono questo schema:
```nginx
server {
    listen 80;  # o la porta ip-provisional dedicata, con ssl
    server_name <nomeapp>.fbosolution.it;

    location /api/internal/ {
        allow 127.0.0.1;
        deny all;
        proxy_pass http://unix:/run/<nomeapp>/gunicorn.sock;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/<nomeapp>/app/staticfiles/;
    }

    location / {
        proxy_pass http://unix:/run/<nomeapp>/gunicorn.sock;
        proxy_set_header Host $http_host;   # $http_host, non $host: altrimenti il CSRF check di Django fallisce quando la porta non è standard
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Deploy di un aggiornamento

```bash
ssh mkremote-vps
cd /opt/<nomeapp>/app
sudo -u <nomeapp> git pull origin main
sudo -u <nomeapp> venv/bin/pip install -r requirements.txt
sudo -u <nomeapp> venv/bin/python manage.py migrate
sudo -u <nomeapp> venv/bin/python manage.py collectstatic --noinput
systemctl restart <nomeapp>-web.service
```

Alcune app (es. FBOPreventivi) hanno anche un `deploy.sh` alla radice del
repo che automatizza git push + comandi VPS via SSH (host `mkremote-vps`
già configurato in `~/.ssh/config`), con opzioni `-m`, `-s`, `-g`. Comodo da
replicare per una nuova app quando il deploy manuale è rodato.

## File di tracciamento del progetto (convenzioni trasversali)

- **`REDFLAG_REPORT.md`**: generato dalla skill `redflag`, un report per
  sessione con segnalazioni FBOFlag esaminate + causa + fix. Non scriverlo a
  mano, lo produce la skill.
- **`STATO.md`** / **`LOG_PRODUZIONE.md`** / **`DA_RIVEDERE.md`**: usati da
  alcuni progetti (Cerberix, FBOAIGate, Squadfy) per tracciare avanzamento,
  log delle modifiche "in produzione" e dubbi aperti. Attivarli con le skill
  `cerberix`/`produzione` quando serve, non è un file obbligatorio per ogni
  app.
- **`.gitignore`**: sempre escludere `venv/`, `db.sqlite3` (a volte
  versionato in dev, mai in prod), `.env`, `staticfiles/`, `media/` (salvo
  eccezioni).

## Checklist rapida per una nuova app FBO

1. Django project + app di dominio, **niente Cliente locale** — usa
   `portal_client.py` per risolvere `client_id` dal Portale.
2. `accounts/` con le due view interne per la gestione utenti da parte del
   Portale.
3. `.env.example` con tutte le variabili commentate (vedi pattern sopra):
   `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
   `INTERNAL_API_TOKEN`, `PORTAL_INTERNAL_BASE_URL`, `PORTAL_API_TOKEN`,
   `PORTAL_PUBLIC_URL`, `PORTAL_INTERNAL_CA_CERT`, più
   `MASTER_ENCRYPTION_KEY` se c'è cifratura, `CELERY_BROKER_URL`/
   `CELERY_RESULT_BACKEND` (db Redis dedicato) se c'è coda async.
4. `deploy/` con: `nginx-<nomeapp>-ip-provisional.conf` (porta dedicata
   libera), `nginx-<nomeapp>.conf` (finale a sottodominio),
   `<nomeapp>-web.service` (+ `-worker.service` se Celery), `README.md` con
   i comandi di provisioning/aggiornamento.
5. `REDFLAG_REPORT.md` vuoto/creato dalla prima sessione redflag.
6. Registrare la nuova app nel Portale (modello `AppLink`, via `/admin/`)
   una volta deployata.
