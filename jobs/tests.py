import json
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings

from . import publishing, rendering, tasks
from .models import ApiClient, Destinazione, Job, Template


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


TEST_MEDIA_ROOT = Path('/tmp/postnect-test-media-api')
# Chiave Fernet fissa, valida solo per i test.
TEST_MASTER_ENCRYPTION_KEY = 'PLBc2vqx0y1QwUE7BbNQEuOwuiuMYFOm1Jr8-hZ8LFI='


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, MASTER_ENCRYPTION_KEY=TEST_MASTER_ENCRYPTION_KEY)
class ApiTestBase(TestCase):
    CLIENT_A = '11111111-1111-1111-1111-111111111111'
    CLIENT_B = '22222222-2222-2222-2222-222222222222'

    def setUp(self):
        self.api_client_a = ApiClient.objects.create(client_id=self.CLIENT_A)
        self.api_client_b = ApiClient.objects.create(client_id=self.CLIENT_B)
        self.template_a = Template.objects.create(
            client_id=self.CLIENT_A, nome='Template A',
            html_content='<h1>{{avversario}} {{risultato}}</h1>',
            campi_richiesti=['avversario', 'risultato'],
        )
        self.destinazione_a = Destinazione.objects.create(
            client_id=self.CLIENT_A, page_id='123456', nome_descrittivo='Pagina test A',
        )
        self.destinazione_a.access_token = 'token-segreto'
        self.destinazione_a.save()

    def _headers(self, api_key):
        return {'HTTP_X_API_KEY': api_key} if api_key is not None else {}


class AutenticazioneApiTests(ApiTestBase):
    def test_genera_senza_api_key(self):
        resp = self.client.post('/genera', data=json.dumps({'template_id': self.template_a.pk}),
                                 content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_genera_con_api_key_non_valida(self):
        resp = self.client.post('/genera', data=json.dumps({'template_id': self.template_a.pk}),
                                 content_type='application/json', **self._headers('chiave-inventata'))
        self.assertEqual(resp.status_code, 401)

    def test_genera_con_api_key_di_client_disattivato(self):
        self.api_client_a.attivo = False
        self.api_client_a.save()
        resp = self.client.post('/genera', data=json.dumps({'template_id': self.template_a.pk}),
                                 content_type='application/json', **self._headers(self.api_client_a.api_key))
        self.assertEqual(resp.status_code, 401)

    def test_job_detail_richiede_auth(self):
        resp = self.client.get('/job/1/')
        self.assertEqual(resp.status_code, 401)


class IsolamentoClientiTests(ApiTestBase):
    def test_cliente_b_non_puo_usare_template_di_cliente_a(self):
        resp = self.client.post(
            '/genera', data=json.dumps({'template_id': self.template_a.pk, 'dati': {}}),
            content_type='application/json', **self._headers(self.api_client_b.api_key),
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Job.objects.filter(client_id=self.CLIENT_B).exists())

    def test_cliente_b_non_puo_usare_destinazione_di_cliente_a(self):
        template_b = Template.objects.create(
            client_id=self.CLIENT_B, nome='Template B', html_content='<h1>{{x}}</h1>', campi_richiesti=['x'],
        )
        resp = self.client.post(
            '/pubblica', data=json.dumps({
                'template_id': template_b.pk, 'destinazione_id': self.destinazione_a.pk,
                'dati': {'x': '1'}, 'caption': 'ciao',
            }),
            content_type='application/json', **self._headers(self.api_client_b.api_key),
        )
        self.assertEqual(resp.status_code, 404)

    def test_job_detail_non_visibile_a_cliente_diverso(self):
        job = Job.objects.create(client_id=self.CLIENT_A, template=self.template_a, dati={})
        resp = self.client.get(f'/job/{job.pk}/', **self._headers(self.api_client_b.api_key))
        self.assertEqual(resp.status_code, 404)


class GeneraPubblicaViewTests(ApiTestBase):
    @patch('jobs.views.tasks.process_job.delay')
    def test_genera_crea_job_e_lo_accoda(self, mock_delay):
        resp = self.client.post(
            '/genera', data=json.dumps({'template_id': self.template_a.pk, 'dati': {'avversario': 'Inter', 'risultato': '2-1'}}),
            content_type='application/json', **self._headers(self.api_client_a.api_key),
        )
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        self.assertEqual(body['stato'], 'in_coda')
        job = Job.objects.get(pk=body['job_id'])
        self.assertEqual(str(job.client_id), self.CLIENT_A)
        self.assertIsNone(job.destinazione)
        mock_delay.assert_called_once_with(job.pk)

    @patch('jobs.views.tasks.process_job.delay')
    def test_pubblica_crea_job_con_destinazione_e_caption(self, mock_delay):
        resp = self.client.post(
            '/pubblica', data=json.dumps({
                'template_id': self.template_a.pk, 'destinazione_id': self.destinazione_a.pk,
                'dati': {'avversario': 'Milan', 'risultato': '1-1'}, 'caption': 'Che partita!',
            }),
            content_type='application/json', **self._headers(self.api_client_a.api_key),
        )
        self.assertEqual(resp.status_code, 202)
        job = Job.objects.get(pk=resp.json()['job_id'])
        self.assertEqual(job.destinazione_id, self.destinazione_a.pk)
        self.assertEqual(job.caption, 'Che partita!')
        mock_delay.assert_called_once_with(job.pk)


class FlussoCompletoGeneraPubblicaTests(ApiTestBase):
    """Flusso completo genera -> pubblica, eseguendo il task Celery in
    modo sincrono (senza broker) e mockando il publisher social."""

    def test_process_job_genera_e_pubblica_su_mock_publisher(self):
        job = Job.objects.create(
            client_id=self.CLIENT_A, template=self.template_a, destinazione=self.destinazione_a,
            dati={'avversario': 'Juventus', 'risultato': '3-0'}, caption='Vittoria netta',
        )

        with patch.object(publishing.FacebookPublisher, 'pubblica', return_value='fb_post_123') as mock_pubblica:
            stato_finale = tasks.process_job(job.pk)

        job.refresh_from_db()
        self.assertEqual(stato_finale, 'pubblicato')
        self.assertEqual(job.stato, 'pubblicato')
        self.assertEqual(job.post_id_risultante, 'fb_post_123')
        self.assertTrue(job.immagine_path)
        mock_pubblica.assert_called_once()

    def test_process_job_senza_destinazione_si_ferma_a_generato(self):
        job = Job.objects.create(
            client_id=self.CLIENT_A, template=self.template_a,
            dati={'avversario': 'Roma', 'risultato': '0-0'},
        )

        stato_finale = tasks.process_job(job.pk)

        job.refresh_from_db()
        self.assertEqual(stato_finale, 'generato')
        self.assertIsNone(job.post_id_risultante)
