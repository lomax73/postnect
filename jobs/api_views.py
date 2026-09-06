import json

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import tasks
from .models import ApiClient, Destinazione, Job, Template


def _autentica(request):
    """Verifica l'header X-API-Key contro ApiClient.api_key. Ritorna
    l'ApiClient attivo corrispondente, o None se mancante/non valido."""
    api_key = request.headers.get('X-Api-Key')
    if not api_key:
        return None
    return ApiClient.objects.filter(api_key=api_key, attivo=True).first()


@method_decorator(csrf_exempt, name='dispatch')
class ApiKeyAuthView(View):
    """Base per le view autenticate con X-API-Key. self.api_client è
    disponibile in get/post una volta passato dispatch()."""

    def dispatch(self, request, *args, **kwargs):
        api_client = _autentica(request)
        if api_client is None:
            return JsonResponse({'detail': 'API key mancante o non valida.'}, status=401)
        self.api_client = api_client
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _json_body(request):
        try:
            return json.loads(request.body), None
        except ValueError:
            return None, JsonResponse({'detail': 'JSON non valido.'}, status=400)


def _serialize_job(job, request):
    immagine_url = None
    if job.immagine_path:
        immagine_url = request.build_absolute_uri(settings.MEDIA_URL + job.immagine_path)
    return {
        'job_id': job.pk,
        'stato': job.stato,
        'immagine_path': job.immagine_path,
        'immagine_url': immagine_url,
        'post_id_risultante': job.post_id_risultante,
        'errore_messaggio': job.errore_messaggio,
    }


class GeneraView(ApiKeyAuthView):
    def post(self, request):
        data, errore = self._json_body(request)
        if errore:
            return errore

        template_id = data.get('template_id')
        template = Template.objects.filter(
            pk=template_id, client_id=self.api_client.client_id, attivo=True,
        ).first()
        if template is None:
            return JsonResponse({'detail': 'Template non trovato.'}, status=404)

        job = Job.objects.create(
            client_id=self.api_client.client_id,
            template=template,
            dati=data.get('dati') or {},
        )
        tasks.process_job.delay(job.pk)
        return JsonResponse({'job_id': job.pk, 'stato': job.stato}, status=202)


class PubblicaView(ApiKeyAuthView):
    def post(self, request):
        data, errore = self._json_body(request)
        if errore:
            return errore

        template = Template.objects.filter(
            pk=data.get('template_id'), client_id=self.api_client.client_id, attivo=True,
        ).first()
        if template is None:
            return JsonResponse({'detail': 'Template non trovato.'}, status=404)

        destinazione = Destinazione.objects.filter(
            pk=data.get('destinazione_id'), client_id=self.api_client.client_id,
        ).first()
        if destinazione is None:
            return JsonResponse({'detail': 'Destinazione non trovata.'}, status=404)

        job = Job.objects.create(
            client_id=self.api_client.client_id,
            template=template,
            dati=data.get('dati') or {},
            destinazione=destinazione,
            caption=data.get('caption') or '',
        )
        tasks.process_job.delay(job.pk)
        return JsonResponse({'job_id': job.pk, 'stato': job.stato}, status=202)


class JobDetailView(ApiKeyAuthView):
    def get(self, request, pk):
        job = Job.objects.filter(pk=pk, client_id=self.api_client.client_id).first()
        if job is None:
            return JsonResponse({'detail': 'Job non trovato.'}, status=404)
        return JsonResponse(_serialize_job(job, request))
