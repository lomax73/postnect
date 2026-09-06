# Deploy sul VPS

Stesso pattern delle altre app della famiglia FBO (repo separato, utente di
sistema dedicato, venv proprio, sottodominio proprio) — vedi
`struttura_app_fbo.md` nella root del progetto per i dettagli generali.
Differenza rispetto alle app solo-web: Postnect ha anche un **worker
Celery** (rendering Playwright + pubblicazione social), da tenere in
esecuzione come unit systemd separata.

## Stato attuale

**In produzione su dominio dal 2026-09-06**: `https://postnect.fbosolution.it/`
(certificato Let's Encrypt, redirect 80→443). `postnect-web.service` e
`postnect-worker.service` attivi. Flusso end-to-end verificato (API → Celery
→ Playwright → immagine da `/media/`), login dashboard ok, integrazione col
Portale ok in entrambe le direzioni.

Storico:
- 2026-09-04: primo deploy ip-provisional su `https://94.177.161.127:8454/`.
- 2026-09-04: integrazione Portale — `PORTAL_API_TOKEN` valorizzato
  (copiato server-side da `INTERNAL_API_TOKEN` del Portale), `AppLink`
  registrato (slug `postnect`, icona `postnect.svg` in `static/img/`,
  `api_token` = `INTERNAL_API_TOKEN` di Postnect). Verificato nei due sensi
  (`portal_client.list_clienti()` e `useradmin.services.list_users()`).
- 2026-09-06: migrazione a `postnect.fbosolution.it`. `AppLink.url`
  aggiornato, `AppLink.internal_ca_cert` → `/etc/ssl/pinned-certs/postnect.pem`,
  porta 8454 chiusa su UFW (l'API interna gira su `127.0.0.1:8454`).

Cosa manca ancora (non bloccante):
- Nessun cliente/template/destinazione reale creato: solo dati di test
  (creati e poi rimossi) durante le verifiche.
- Collegamento con Squadfy (gancio già pronto lato Squadfy:
  `partite.servizi.partite_da_pubblicare()` + campo `Partita.pubblicato_social`).

Note di configurazione verificate sul VPS (vedi anche `struttura_app_fbo.md`):
- Porta **8454** assegnata a Postnect, ora **bind solo su `127.0.0.1`** e
  chiusa su UFW (era pubblica durante l'ip-provisional).
- Db Redis **3** (0/1 MKRemote, 2 FBOMailer). Redis richiede autenticazione
  (`redis://:<password>@...`, stessa password di MKRemote/FBOMailer).
- RAM del VPS limitata (3.8 GiB, ~1.7 GiB liberi): Chromium headless è il
  processo più pesante — se il worker va in OOM, `celery -A postnect worker
  --concurrency=1`.
- **`chmod o+x /opt/postnect` necessario** (già applicato): senza, Nginx
  (`www-data`) non attraversa la home per `/static/`/`/media/` → 403.
- **Migrazione al dominio**: cambiando `listen 8454` da `0.0.0.0` a
  `127.0.0.1`, `systemctl reload nginx` fallisce in silenzio (il worker
  vecchio tiene la porta). Serve `systemctl restart nginx`.

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
# + apertura porta su UFW: ufw allow 8454/tcp
```

## Migrazione a dominio (fatta il 2026-09-06)

Procedura seguita, per riferimento se si rifà da capo o per un'altra app:

```bash
# 1. vhost porta 80 per ACME + redirect
cp deploy/nginx-postnect-80.conf /etc/nginx/sites-available/postnect-80
ln -sf /etc/nginx/sites-available/postnect-80 /etc/nginx/sites-enabled/postnect-80
nginx -t && systemctl reload nginx

# 2. certificato Let's Encrypt (webroot, non --nginx: non riscrive i vhost)
certbot certonly --webroot -w /var/www/html -d postnect.fbosolution.it \
    --non-interactive --agree-tos -m f.lomazzi@fbosolution.it

# 3. vhost finale (443 pubblico + 127.0.0.1:8454 interno)
cp deploy/nginx-postnect.conf /etc/nginx/sites-available/postnect
nginx -t && systemctl restart nginx   # restart, NON reload (vedi nota sopra)

# 4. cert pinnato per l'API interna del Portale (RedFlag id 87)
cp /etc/letsencrypt/live/postnect.fbosolution.it/fullchain.pem /etc/ssl/pinned-certs/postnect.pem
chmod 644 /etc/ssl/pinned-certs/postnect.pem
# + aggiungere la riga cp corrispondente in
#   /etc/letsencrypt/renewal-hooks/deploy/copy-pinned-certs.sh

# 5. .env: aggiungere il dominio a DJANGO_ALLOWED_HOSTS, restart servizi
sudo -u postnect sed -i 's|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=postnect.fbosolution.it,94.177.161.127,localhost,127.0.0.1|' /opt/postnect/app/.env
systemctl restart postnect-web postnect-worker

# 6. AppLink nel Portale: url -> https://postnect.fbosolution.it/,
#    internal_ca_cert -> /etc/ssl/pinned-certs/postnect.pem

# 7. chiudere la porta pubblica
ufw delete allow 8454/tcp
```

## Registrazione nel Portale

Aggiungere Postnect al Portale FBO come `AppLink` (via `/admin/` del Portale)
così compare come card nella home. Per la gestione utenti centralizzata,
`AppLink.api_token` deve valere quanto `INTERNAL_API_TOKEN` nel `.env` di
Postnect; per l'anagrafica clienti, `PORTAL_API_TOKEN` nel `.env` di Postnect
deve valere quanto `INTERNAL_API_TOKEN` nel `.env` del Portale.

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
