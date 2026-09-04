# Postnect — prompt per Claude Code

Servizio self-hosted che genera immagini a partire da un template
(HTML/CSS con placeholder) e dati, e opzionalmente le pubblica su social.
Nasce per generare grafiche di risultati calcistici ma è progettato per
essere riusato da altri progetti (multi-cliente). È un'app della famiglia
FBO, deployata sullo stesso VPS delle altre e collegata a FBOPortal.

**Prima di iniziare**: leggi `struttura_app_fbo.md` in questa cartella —
raccoglie stack, convenzioni e pattern di deploy già in uso in tutte le
altre app FBO (FBOPortal, FBOMailer, FBOPreventivi, FBOLeads, FBOAIGate...).
Postnect deve seguirli, non introdurre uno stack nuovo.

Usa questi prompt in sequenza, in sessioni separate di Claude Code. Ogni
prompt assume che il precedente sia stato completato.

---

## Prompt 1 — Scaffolding e modelli

Crea un nuovo progetto Django chiamato `postnect`, seguendo lo stack e le
convenzioni descritte in `struttura_app_fbo.md`:

- Django `<6.0`, SQLite, `python-dotenv`, `gunicorn`
- Celery + Redis per i job di rendering/pubblicazione (asincroni, mai in
  request-response diretto) — usa un numero di database Redis **non ancora
  occupato** dalle altre app (vedi tabella in `struttura_app_fbo.md`,
  verificare comunque sul VPS prima di fissarlo)
- Struttura a più app Django: `accounts/` (API interna gestione utenti,
  pattern standard), `templates_app/` o nome equivalente per Template/Job/
  Destinazione (evita di chiamare l'app Django `templates` per non confliggere
  con la cartella `templates/` dei template HTML Django)
- **Nessun modello `Cliente` locale**: riusa l'anagrafica clienti del
  Portale. Copia/adatta `preventivi/portal_client.py` (da
  `FBOPreventivi`) per risolvere `client_id` (UUID) via
  `PORTAL_INTERNAL_BASE_URL` + `PORTAL_API_TOKEN`, incluso il pinning del
  certificato self-signed

Implementa questi modelli:

**Template**
- `client_id` (UUID, riferimento al cliente nel Portale — niente FK locale)
- `nome` (str)
- `html_content` (text) — il markup con placeholder tipo `{{risultato}}`
- `css_content` (text, nullable)
- `campi_richiesti` (JSON) — schema dei placeholder attesi, es.
  `["avversario", "risultato", "data"]`
- `attivo` (bool, default True)

**Destinazione**
- `client_id` (UUID)
- `piattaforma` (str, choices: "facebook", per ora solo questa)
- `page_id` (str)
- `access_token` (str, **cifrato a riposo** con Fernet, chiave in
  `MASTER_ENCRYPTION_KEY` — stesso nome env usato da FBOMailer/FBOLeads)
- `nome_descrittivo` (str) — es. "Pagina FB ASD Calcio Olgiate"

**Job**
- `client_id` (UUID)
- `template` (FK a Template)
- `dati` (JSON) — i valori per i placeholder
- `stato` (str, choices: in_coda, generato, pubblicato, errore)
- `immagine_path` (str, nullable)
- `destinazione` (FK a Destinazione, nullable) — nullo se è solo generazione
- `post_id_risultante` (str, nullable)
- `errore_messaggio` (text, nullable)
- `created_at`, `updated_at`

**ApiClient** (per l'autenticazione delle chiamate esterne a Postnect)
- `client_id` (UUID, deve corrispondere a un cliente esistente nel Portale)
- `api_key` (str, unique, generata random alla creazione)
- `attivo` (bool, default True)

Genera le migrazioni iniziali. Crea anche `.env.example` seguendo lo schema
in `struttura_app_fbo.md` (incluse le variabili `PORTAL_*`,
`INTERNAL_API_TOKEN`, `MASTER_ENCRYPTION_KEY`, `CELERY_*`). Non implementare
ancora API o rendering — solo scaffolding e modelli in questo step.

---

## Prompt 2 — Motore di rendering

Nel progetto `postnect` già esistente, implementa il rendering delle
immagini:

- Usa Playwright (headless Chromium) per fare uno screenshot di un template
  HTML con i dati del Job iniettati nei placeholder (sostituzione semplice
  `{{campo}}` → valore, valida prima che tutti i `campi_richiesti` del
  Template siano presenti nei `dati` del Job — se manca qualcosa, il Job va
  in stato `errore` con messaggio chiaro)
- Il rendering gira in un **task Celery**, mai in request-response diretto
  (può richiedere qualche secondo)
- L'immagine generata va salvata in `media/` (storage locale, come le altre
  app FBO — niente S3 finché non serve davvero) e il path va scritto su
  `Job.immagine_path`
- Al termine, `Job.stato` passa a `generato`

Aggiungi test che verifichino: sostituzione corretta dei placeholder,
gestione dell'errore quando un campo richiesto manca, che il job cambi stato
correttamente.

---

## Prompt 3 — Pubblicazione e API REST

Nel progetto `postnect`, aggiungi:

### Modulo di pubblicazione
Un'interfaccia astratta `SocialPublisher` con un metodo `pubblica(immagine,
caption, destinazione) -> post_id`, e un'implementazione concreta
`FacebookPublisher` che usa la Graph API (POST a `/{page_id}/photos` con
`caption` e il token della Destinazione, decifrato al momento dell'uso).
Pensala così da poter aggiungere `InstagramPublisher` in futuro senza
toccare il resto del sistema.

### API REST
Autenticazione: header `X-API-Key`, verificato contro `ApiClient.api_key`
(non contro un modello Cliente locale — vedi Prompt 1).

- `POST /genera` — body: `{template_id, dati}`. Crea un Job, lo accoda per
  il rendering (task Celery), ritorna `{job_id, stato}`
- `POST /pubblica` — body: `{template_id, dati, destinazione_id, caption}`.
  Come sopra ma accoda anche la pubblicazione dopo il rendering
- `GET /job/{id}` — ritorna stato, immagine_path (se generato),
  post_id_risultante (se pubblicato), errore_messaggio (se in errore)

Tutti gli endpoint devono verificare che template_id/destinazione_id
appartengano allo stesso `client_id` dell'`ApiClient` autenticato (mai
permettere a un cliente di usare risorse di un altro).

Aggiungi test per: autenticazione mancante/invalida, isolamento tra clienti
(cliente A non può usare template di cliente B), flusso completo genera →
pubblica su un mock del publisher.

---

## Prompt 4 — Editor template (dashboard minimale)

Nel progetto `postnect`, aggiungi un'interfaccia di gestione interna
(uso tuo, non del cliente finale) usando **Django admin** — coerente con
FBOPreventivi/FBOLeads, gratis e già presente nello stack:

- Creare/modificare `ApiClient` (rigenerazione api_key)
- Creare/modificare Template (con anteprima live del rendering se possibile,
  altrimenti anche solo un'azione admin "genera anteprima" che chiama
  internamente il motore di rendering con dati di esempio)
- Creare/modificare Destinazioni (campo token mascherato in admin, mai
  mostrato in chiaro dopo il salvataggio)
- Vedere la lista dei Job recenti con stato ed eventuali errori (list_display
  + filtri nel Django admin)

Aggiungi anche `deploy/` (nginx ip-provisional + finale, `postnect-web.service`
+ `postnect-worker.service` per Celery, README) seguendo esattamente il
template descritto in `struttura_app_fbo.md`, con una porta dedicata libera
per l'ip-provisional.
