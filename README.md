# Postnect

Servizio self-hosted che genera immagini a partire da un template
(HTML/CSS con placeholder) e dati, e opzionalmente le pubblica su social
(per ora Facebook). Nasce per generare grafiche di risultati calcistici ma
è progettato per essere riusato da altri progetti (multi-cliente). App
della famiglia FBO — vedi `struttura_app_fbo.md` per stack e convenzioni
condivise con le altre app collegate a FBOPortal.

## Sviluppo locale

```
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/playwright install chromium   # scarica il browser headless usato dal motore di rendering
cp .env.example .env
venv/bin/python manage.py migrate
venv/bin/python manage.py createsuperuser
venv/bin/python manage.py runserver
```

Serve anche Redis in locale per Celery (rendering/pubblicazione in
background, a partire dal Prompt 2):
```
redis-server
venv/bin/celery -A postnect worker -l info
```

## Stato

- **Prompt 1** (scaffolding e modelli): completato. `jobs/` (Template,
  Destinazione, Job, ApiClient — nessun modello Cliente locale, si risolve
  `client_id` dal Portale via `jobs/portal_client.py`), `accounts/` (API
  interna gestione utenti per il Portale).
- **Prompt 2** (motore di rendering): completato. `jobs/rendering.py`
  (sostituzione placeholder + validazione campi_richiesti + screenshot
  Playwright), immagini salvate in `media/renders/`.
- **Prompt 3** (pubblicazione e API REST): completato. `jobs/publishing.py`
  (`SocialPublisher` astratto, `FacebookPublisher` via Graph API),
  `jobs/tasks.py` (task Celery unico `process_job`: rendering + pubblicazione
  se il Job ha una Destinazione), API REST autenticata via header
  `X-API-Key` (`POST /genera`, `POST /pubblica`, `GET /job/{id}`), isolamento
  tra clienti verificato su ogni endpoint. Test in `jobs/tests.py`.
- **Prompt 4** (dashboard admin): completato. Gestione di `ApiClient`
  (azione "rigenera API key"), `Template` (azione "genera anteprima" con
  dati di esempio), `Destinazione` (token mascherato, non richiesto in
  modifica), `Job` (sola lettura, stato colorato, filtri) tramite Django
  admin — vedi `jobs/admin.py`. `deploy/` creato seguendo il pattern in
  `struttura_app_fbo.md`.

Tutti i prompt di `prompt-claude-code-postnect.md` sono completati. 24 test,
tutti verdi (`venv/bin/python manage.py test`).

## Deploy

**In produzione (ip-provisional)**: `https://94.177.161.127:8454/`,
deployato e verificato end-to-end il 2026-09-04. Vedi `deploy/README.md`
per stato dettagliato e cosa manca ancora (in particolare `PORTAL_API_TOKEN`
da completare a mano).
