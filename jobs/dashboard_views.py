"""Dashboard interna (uso tuo, non del cliente finale) per gestire
Template/Destinazione/ApiClient e vedere i Job recenti — autenticazione
via sessione Django (login richiesto), non X-API-Key come le viste in
api_views.py."""

import secrets

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from . import portal_client, rendering
from .forms import ApiClientForm, DestinazioneForm, TemplateForm
from .models import ApiClient, Destinazione, Job, Template


class JobListView(LoginRequiredMixin, ListView):
    model = Job
    template_name = 'jobs/job_list.html'
    context_object_name = 'jobs'
    paginate_by = 50

    def get_queryset(self):
        qs = Job.objects.select_related('template', 'destinazione').order_by('-created_at')
        stato = self.request.GET.get('stato')
        if stato:
            qs = qs.filter(stato=stato)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stato_filtro'] = self.request.GET.get('stato', '')
        context['stati'] = Job.STATO_CHOICES
        return context


class TemplateListView(LoginRequiredMixin, ListView):
    model = Template
    template_name = 'jobs/template_list.html'
    context_object_name = 'templates'

    def get_queryset(self):
        return Template.objects.order_by('nome')


class TemplateCreateView(LoginRequiredMixin, CreateView):
    model = Template
    form_class = TemplateForm
    template_name = 'jobs/template_form.html'
    success_url = reverse_lazy('template-list')


class TemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = Template
    form_class = TemplateForm
    template_name = 'jobs/template_form.html'
    success_url = reverse_lazy('template-list')


class TemplateDeleteView(LoginRequiredMixin, DeleteView):
    model = Template
    template_name = 'jobs/template_confirm_delete.html'
    success_url = reverse_lazy('template-list')


class TemplateAnteprimaView(LoginRequiredMixin, View):
    """Solo POST: genera un'anteprima sincrona del Template con dati di
    esempio (vedi rendering.genera_job_anteprima)."""

    def post(self, request, pk):
        template = get_object_or_404(Template, pk=pk)
        job = rendering.genera_job_anteprima(template)
        if job.stato == 'generato':
            messages.success(request, f'Anteprima di «{template.nome}» generata.')
        else:
            messages.error(request, f'Anteprima di «{template.nome}» fallita: {job.errore_messaggio}')
        return redirect('template-list')


class DestinazioneListView(LoginRequiredMixin, ListView):
    model = Destinazione
    template_name = 'jobs/destinazione_list.html'
    context_object_name = 'destinazioni'

    def get_queryset(self):
        return Destinazione.objects.order_by('nome_descrittivo')


class DestinazioneCreateView(LoginRequiredMixin, CreateView):
    model = Destinazione
    form_class = DestinazioneForm
    template_name = 'jobs/destinazione_form.html'
    success_url = reverse_lazy('destinazione-list')


class DestinazioneUpdateView(LoginRequiredMixin, UpdateView):
    model = Destinazione
    form_class = DestinazioneForm
    template_name = 'jobs/destinazione_form.html'
    success_url = reverse_lazy('destinazione-list')


class DestinazioneDeleteView(LoginRequiredMixin, DeleteView):
    model = Destinazione
    template_name = 'jobs/destinazione_confirm_delete.html'
    success_url = reverse_lazy('destinazione-list')


class ApiClientListView(LoginRequiredMixin, ListView):
    model = ApiClient
    template_name = 'jobs/apiclient_list.html'
    context_object_name = 'api_clients'

    def get_queryset(self):
        api_clients = list(ApiClient.objects.order_by('-created_at'))
        # Postnect non ha un modello Cliente locale: il nome va risolto
        # dall'anagrafica condivisa del Portale. Una sola chiamata (lista
        # completa) invece di una per ApiClient, con fallback silenzioso
        # se il Portale non risponde (l'id resta comunque visibile).
        try:
            nomi_per_id = {str(c['id']): c['ragione_sociale'] for c in portal_client.list_clienti()}
        except portal_client.PortalUnavailableError:
            nomi_per_id = {}
            messages.warning(self.request, 'Impossibile contattare il Portale per i nomi dei clienti: mostrati solo gli ID.')
        for api_client in api_clients:
            api_client.nome_cliente = nomi_per_id.get(str(api_client.client_id))
        return api_clients


class ApiClientCreateView(LoginRequiredMixin, CreateView):
    model = ApiClient
    form_class = ApiClientForm
    template_name = 'jobs/apiclient_form.html'
    success_url = reverse_lazy('apiclient-list')

    def form_valid(self, form):
        response = super().form_valid(form)
        # La api_key è generata random e mai più leggibile in chiaro dopo
        # questa risposta (mascherata ovunque nella lista): va mostrata per
        # intero solo adesso, una tantum, perché l'utente possa copiarla.
        messages.success(
            self.request,
            f'Client creato. API key (copiala ora, non sarà più mostrata per intero): {self.object.api_key}',
        )
        return response


class ApiClientDeleteView(LoginRequiredMixin, DeleteView):
    model = ApiClient
    template_name = 'jobs/apiclient_confirm_delete.html'
    success_url = reverse_lazy('apiclient-list')


class ApiClientRigeneraView(LoginRequiredMixin, View):
    """Solo POST: rigenera la api_key di un ApiClient."""

    def post(self, request, pk):
        api_client = get_object_or_404(ApiClient, pk=pk)
        api_client.api_key = secrets.token_urlsafe(32)
        api_client.save(update_fields=['api_key'])
        messages.success(
            request,
            f'API key rigenerata (copiala ora, non sarà più mostrata per intero): {api_client.api_key}',
        )
        return redirect('apiclient-list')
