# Deploy sul VPS

Stesso pattern delle altre app della famiglia FBO (repo separato, utente di
sistema dedicato, venv proprio, sottodominio proprio) — vedi
`struttura_app_fbo.md` nella root del progetto per i dettagli generali.
Differenza rispetto alle app solo-web: Postnect ha anche un **worker
Celery** (rendering Playwright + pubblicazione social), da tenere in
esecuzione come unit systemd separata.

## Stato attuale

Verificato via SSH su `mkremote-vps` il 2026-09-04:
- **Porta 8454** (usata in `nginx-postnect-ip-provisional.conf`) confermata
  libera — occupate: 8443-8453 (Portale, FiberReport, Preventivi,
  RackReport, NetVault, Squadfy, MKRemote, FBOMailer, FBOLeads, FBOAIGate,
  Sicufy).
- **Db Redis 3** (usato di default per `CELERY_BROKER_URL`/
  `CELERY_RESULT_BACKEND`) confermato libero — occupati: 0/1 (MKRemote),
  2 (FBOMailer). Redis richiede autenticazione (`redis://:<password>@...`,
  la password è quella già nell'`.env` di MKRemote/FBOMailer sul VPS).
- **RAM del VPS limitata** (3.8 GiB totali, ~1.7 GiB liberi): Chromium
  headless (Playwright) è il processo più pesante di questa app — se il
  worker va in OOM, valutare `celery -A postnect worker --concurrency=1`
  invece del default. Vedi `struttura_app_fbo.md` per i dettagli.

Se in futuro queste risorse risultassero rioccupate da un'altra app nel
frattempo, aggiornare di conseguenza `nginx-postnect-ip-provisional.conf`
e/o `.env` prima di procedere.

## Provisioning iniziale (una tantum)

```bash
# da root sul VPS
adduser --system --group --home /opt/postnect postnect
mkdir -p /opt/postnect/app
chown postnect:postnect /opt/postnect/app

sudo -u postnect git clone <url-repo> /opt/postnect/app
cd /opt/postnect/app
sudo -u postnect python3 -m venv venv
sudo -u postnect venv/bin/pip install -r requirements.txt

# Playwright: scarica il browser headless usato dal motore di rendering.
# Richiede anche le dipendenze di sistema di Chromium (prima volta):
sudo venv/bin/playwright install-deps chromium
sudo -u postnect venv/bin/playwright install chromium

cp .env.example .env   # valorizzare tutto — DJANGO_DEBUG=false, PORTAL_*,
                        # INTERNAL_API_TOKEN, MASTER_ENCRYPTION_KEY, CELERY_*
                        # (vedi commenti in .env.example per ogni variabile
                        # e come generarla)
sudo -u postnect venv/bin/python manage.py migrate
sudo -u postnect venv/bin/python manage.py collectstatic --noinput
sudo -u postnect venv/bin/python manage.py createsuperuser

# Certificato self-signed per l'ip-provisional (finché non c'è un dominio):
mkdir -p /etc/ssl/postnect
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout /etc/ssl/postnect/selfsigned.key -out /etc/ssl/postnect/selfsigned.crt \
    -subj "/CN=$(curl -s ifconfig.me)"

cp deploy/postnect-web.service /etc/systemd/system/
cp deploy/postnect-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now postnect-web.service postnect-worker.service

cp deploy/nginx-postnect-ip-provisional.conf /etc/nginx/sites-available/postnect
ln -s /etc/nginx/sites-available/postnect /etc/nginx/sites-enabled/postnect
nginx -t && systemctl reload nginx
# + apertura porta su UFW: ufw allow 8453/tcp
```

Quando sarà disponibile un dominio vero (`postnect.fbosolution.it`), seguire
la stessa procedura di migrazione già usata per Squadfy/Portal (DNS su
Aruba, `certbot --nginx -d postnect.fbosolution.it`, sostituire
`nginx-postnect-ip-provisional.conf` con `nginx-postnect.conf`).

## Registrazione nel Portale

Dopo il primo deploy, aggiungere Postnect al Portale FBO (`AppLink` via
`/admin/` del Portale) così compare come card nella home. Se serve
gestione utenti centralizzata da parte del Portale, verificare che
`INTERNAL_API_TOKEN` qui corrisponda a quanto configurato lato Portale per
questa app.

## Deploy di un aggiornamento

```bash
ssh mkremote-vps
cd /opt/postnect/app
sudo -u postnect git pull origin main
sudo -u postnect venv/bin/pip install -r requirements.txt
sudo -u postnect venv/bin/python manage.py migrate
sudo -u postnect venv/bin/python manage.py collectstatic --noinput
systemctl restart postnect-web.service postnect-worker.service
```
