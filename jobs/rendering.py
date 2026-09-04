"""Motore di rendering: sostituzione placeholder nel Template + screenshot
via Playwright (headless Chromium). Va sempre invocato da un task Celery
(jobs/tasks.py), mai in request-response diretto: uno screenshot può
richiedere qualche secondo."""

import re
from pathlib import Path

from django.conf import settings
from playwright.sync_api import sync_playwright

PLACEHOLDER_RE = re.compile(r'\{\{\s*(\w+)\s*\}\}')

# Dimensioni di default del viewport per lo screenshot (formato social
# standard, 1200x630 — es. Facebook link/photo preview). Non configurabile
# per Template in questo step: se in futuro servirà, aggiungere un campo
# dedicato al modello Template invece di dedurlo dall'HTML.
VIEWPORT_WIDTH = 1200
VIEWPORT_HEIGHT = 630


def campi_mancanti(template, dati):
    """Elenco dei campi in Template.campi_richiesti non presenti come
    chiave in dati. Lista vuota se non manca nulla."""
    dati = dati or {}
    return [campo for campo in template.campi_richiesti if campo not in dati]


def sostituisci_placeholder(html, dati):
    """Sostituzione semplice `{{campo}}` -> valore. I placeholder senza un
    valore corrispondente in dati restano invariati nel markup."""
    dati = dati or {}

    def _replace(match):
        campo = match.group(1)
        if campo in dati:
            return str(dati[campo])
        return match.group(0)

    return PLACEHOLDER_RE.sub(_replace, html)


def _documento_html(html_content, css_content):
    css = f'<style>{css_content}</style>' if css_content else ''
    return f'<!doctype html><html><head><meta charset="utf-8">{css}</head><body>{html_content}</body></html>'


def render_html_to_image(html_content, css_content, output_path):
    """Fa uno screenshot dell'HTML (con CSS inline) e lo salva su
    output_path (PNG). output_path può essere str o Path; le directory
    intermedie vengono create se mancanti."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    documento = _documento_html(html_content, css_content)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT})
            page.set_content(documento, wait_until='load')
            page.screenshot(path=str(output_path), full_page=True)
        finally:
            browser.close()


def esegui_rendering(job):
    """Orchestrazione completa per un Job: valida i campi richiesti,
    sostituisce i placeholder, fa lo screenshot e aggiorna stato/
    immagine_path/errore_messaggio. Non solleva eccezioni verso il
    chiamante: qualunque errore viene scritto sul Job (stato='errore')."""
    template = job.template

    mancanti = campi_mancanti(template, job.dati)
    if mancanti:
        job.stato = 'errore'
        job.errore_messaggio = 'Campi mancanti nei dati del Job: ' + ', '.join(mancanti) + '.'
        job.save(update_fields=['stato', 'errore_messaggio', 'updated_at'])
        return

    html = sostituisci_placeholder(template.html_content, job.dati)

    relative_path = f'renders/job_{job.pk}.png'
    output_path = Path(settings.MEDIA_ROOT) / relative_path

    try:
        render_html_to_image(html, template.css_content, output_path)
    except Exception as exc:  # noqa: BLE001 — qualunque errore di rendering finisce sul Job, non deve far fallire il task Celery
        job.stato = 'errore'
        job.errore_messaggio = f'Errore durante il rendering: {exc}'
        job.save(update_fields=['stato', 'errore_messaggio', 'updated_at'])
        return

    job.immagine_path = relative_path
    job.stato = 'generato'
    job.save(update_fields=['immagine_path', 'stato', 'updated_at'])
