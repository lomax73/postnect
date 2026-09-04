# Deploy sul VPS

Stesso pattern delle altre app della famiglia FBO (repo separato, utente di
sistema dedicato, venv proprio, sottodominio proprio) — vedi
`struttura_app_fbo.md` nella root del progetto per i dettagli generali.
Differenza rispetto alle app solo-web: Postnect ha anche un **worker
Celery** (rendering Playwright + pubblicazione social), da tenere in
esecuzione come unit systemd separata.

## Stato attuale

**Deployato e verificato in produzione (ip-provisional) il 2026-09-04**:
`https://94.177.161.127:8454/` — `postnect-web.service` e
`postnect-worker.service` attivi, flusso end-to-end testato via API
(`POST /genera` → Celery → Playwright → immagine servita da `/media/`).

**Integrazione col Portale completata il 2026-09-04**:
- `PORTAL_API_TOKEN` in `/opt/postnect/app/.env` valorizzato (copiato
  server-side da `INTERNAL_API_TOKEN` del Portale, senza farlo transitare in
  chat), servizi riavviati. Verificato: `jobs.portal_client.list_clienti()`
  risponde con l'anagrafica reale (23 clienti).
- App registrata nel Portale come `AppLink` (slug `postnect`, categoria
  interna, stato "In sviluppo", icona `postnect.svg` caricata in
  `static/img/`, `internal_base_url`/`internal_ca_cert` configurati).
  `api_token` sull'`AppLink` impostato con l'`INTERNAL_API_TOKEN` di
  Postnect: verificato che il Portale riesca a leggere gli utenti di
  Postnect via `useradmin.services.list_users()`.

Cosa manca ancora (non bloccante):
- Nessun cliente/template/destinazione reale creato ancora: solo dati di
  test (creati e poi rimossi) durante la verifica.
- Dominio vero non ancora richiesto (resta sull'IP nudo, porta 8454).

Note di configurazione verificate sul VPS il 2026-09-04 (per riferimento,
vedi anche `struttura_app_fbo.md`):
- Porta **8454** libera (8443-8453 già occupate da altre 11 app).
- Db Redis **3** libero (0/1 MKRemote, 2 FBOMailer). Redis richiede
  autenticazione (`redis://:<password>@...`, stessa password di
  MKRemote/FBOMailer).
- RAM del VPS limitata (3.8 GiB totali, ~1.7 GiB liberi): Chromium headless
  è il processo più pesante di questa app — se il worker va in OOM,
  valutare `celery -A postnect worker --concurrency=1`.
- **`chmod o+x /opt/postnect` necessario** (già applicato): senza, Nginx
  (`www-data`) non può attraversare la home per servire `/static/`/`/media/`
  → 403 anche con config Nginx corretta. Vedi il passo dedicato sotto.

## Provisioning iniziale (una tantum)

```bash
# da root sul VPS
adduser --system --group --home /opt/postnect postnect
chmod o+x /opt/postnect   # altrimenti nginx (www-data) non attraversa la home per /static//media/ -> 403
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
