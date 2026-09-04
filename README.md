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
  Playwright), `jobs/tasks.py` (task Celery `render_job`), immagini salvate
  in `media/renders/`. Test in `jobs/tests.py`.

Pubblicazione, API REST e dashboard admin seguono nei prompt successivi —
vedi `prompt-claude-code-postnect.md`.

## Deploy

Vedi `deploy/README.md` (da creare al Prompt 4, seguendo il pattern in
`struttura_app_fbo.md`).
