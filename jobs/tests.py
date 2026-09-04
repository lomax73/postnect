from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings

from . import rendering
from .models import Job, Template


class SostituzionePlaceholderTests(TestCase):
    def test_sostituisce_placeholder_presenti(self):
        html = '<p>{{avversario}} - {{risultato}} del {{data}}</p>'
        risultato = rendering.sostituisci_placeholder(
            html, {'avversario': 'Inter', 'risultato': '2-1', 'data': '01/09/2026'},
        )
        self.assertEqual(risultato, '<p>Inter - 2-1 del 01/09/2026</p>')

    def test_placeholder_senza_valore_resta_invariato(self):
        html = '<p>{{avversario}} - {{risultato}}</p>'
        risultato = rendering.sostituisci_placeholder(html, {'avversario': 'Inter'})
        self.assertEqual(risultato, '<p>Inter - {{risultato}}</p>')

    def test_tollera_spazi_dentro_le_graffe(self):
        html = '<p>{{ avversario }}</p>'
        risultato = rendering.sostituisci_placeholder(html, {'avversario': 'Milan'})
        self.assertEqual(risultato, '<p>Milan</p>')


class CampiMancantiTests(TestCase):
    def _template(self, campi_richiesti):
        return Template(
            client_id='11111111-1111-1111-1111-111111111111',
            nome='Test',
            html_content='<p>{{avversario}}</p>',
            campi_richiesti=campi_richiesti,
        )

    def test_nessun_campo_mancante(self):
        template = self._template(['avversario', 'risultato'])
        mancanti = rendering.campi_mancanti(template, {'avversario': 'Inter', 'risultato': '2-1'})
        self.assertEqual(mancanti, [])

    def test_campo_mancante_rilevato(self):
        template = self._template(['avversario', 'risultato', 'data'])
        mancanti = rendering.campi_mancanti(template, {'avversario': 'Inter'})
        self.assertEqual(mancanti, ['risultato', 'data'])

    def test_dati_vuoti(self):
        template = self._template(['avversario'])
        mancanti = rendering.campi_mancanti(template, {})
        self.assertEqual(mancanti, ['avversario'])


@override_settings(MEDIA_ROOT=Path('/tmp/postnect-test-media'))
class EseguiRenderingTests(TestCase):
    CLIENT_ID = '11111111-1111-1111-1111-111111111111'

    def _template(self, campi_richiesti=None):
        return Template.objects.create(
            client_id=self.CLIENT_ID,
            nome='Risultato partita',
            html_content='<h1>{{avversario}} {{risultato}}</h1>',
            campi_richiesti=campi_richiesti if campi_richiesti is not None else ['avversario', 'risultato'],
        )

    def test_job_va_in_errore_se_manca_un_campo_richiesto(self):
        template = self._template()
        job = Job.objects.create(client_id=self.CLIENT_ID, template=template, dati={'avversario': 'Inter'})

        rendering.esegui_rendering(job)
        job.refresh_from_db()

        self.assertEqual(job.stato, 'errore')
        self.assertIn('risultato', job.errore_messaggio)
        self.assertIsNone(job.immagine_path)

    def test_job_generato_con_dati_completi(self):
        template = self._template()
        job = Job.objects.create(
            client_id=self.CLIENT_ID, template=template,
            dati={'avversario': 'Inter', 'risultato': '2-1'},
        )

        rendering.esegui_rendering(job)
        job.refresh_from_db()

        self.assertEqual(job.stato, 'generato')
        self.assertEqual(job.errore_messaggio, None)
        self.assertTrue(job.immagine_path)

        immagine = Path('/tmp/postnect-test-media') / job.immagine_path
        self.assertTrue(immagine.exists())
        self.assertGreater(immagine.stat().st_size, 0)

    def test_job_va_in_errore_se_il_rendering_fallisce(self):
        template = self._template()
        job = Job.objects.create(
            client_id=self.CLIENT_ID, template=template,
            dati={'avversario': 'Inter', 'risultato': '2-1'},
        )

        with patch.object(rendering, 'render_html_to_image', side_effect=RuntimeError('boom')):
            rendering.esegui_rendering(job)

        job.refresh_from_db()
        self.assertEqual(job.stato, 'errore')
        self.assertIn('boom', job.errore_messaggio)
