# Deploy sul VPS

Stesso pattern delle altre app della famiglia FBO (repo separato, utente di
sistema dedicato, venv proprio, sottodominio proprio) — vedi
`struttura_app_fbo.md` nella root del progetto per i dettagli generali.
Differenza rispetto alle app solo-web: Postnect ha anche un **worker
Celery** (rendering Playwright + pubblicazione social), da tenere in
esecuzione come unit systemd separata.

## Stato attuale

**Nessuna verifica ancora fatta sul VPS reale.** Prima del primo deploy,
controllare:
- che la **porta 8453** (usata in `nginx-postnect-ip-provisional.conf`) sia
  davvero libera — vedi l'elenco in `struttura_app_fbo.md`, che può essere
  disallineato rispetto a quanto effettivamente configurato oggi;
- che il **db Redis 3** (usato di default per `CELERY_BROKER_URL`/
  `CELERY_RESULT_BACKEND`) non sia già in uso da un'altra app.

Se una delle due risorse è occupata, sceglierne una libera e aggiornare di
conseguenza `nginx-postnect-ip-provisional.conf` e/o `.env`.

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
