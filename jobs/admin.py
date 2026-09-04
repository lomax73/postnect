import secrets

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from . import rendering
from .models import ApiClient, Destinazione, Job, Template


@admin.register(ApiClient)
class ApiClientAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'api_key_mascherata', 'attivo', 'created_at']
    list_filter = ['attivo']
    readonly_fields = ['api_key', 'created_at']
    actions = ['rigenera_api_key']

    def api_key_mascherata(self, obj):
        return f'{obj.api_key[:6]}…' if obj.api_key else '—'
    api_key_mascherata.short_description = 'API key'

    @admin.action(description='Rigenera API key per i client selezionati')
    def rigenera_api_key(self, request, queryset):
        for api_client in queryset:
            api_client.api_key = secrets.token_urlsafe(32)
            api_client.save(update_fields=['api_key'])
        self.message_user(request, f'API key rigenerata per {queryset.count()} client.', messages.SUCCESS)


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ['nome', 'client_id', 'attivo', 'updated_at']
    list_filter = ['attivo']
    search_fields = ['nome', 'client_id']
    actions = ['genera_anteprima']

    @admin.action(description='Genera anteprima (dati di esempio)')
    def genera_anteprima(self, request, queryset):
        for template in queryset:
            dati_esempio = {campo: f'esempio {campo}' for campo in template.campi_richiesti}
            job = Job.objects.create(client_id=template.client_id, template=template, dati=dati_esempio)
            # Sincrono (non accodato su Celery): un'anteprima admin deve
            # essere immediata, non ha senso farla passare dal worker.
            rendering.esegui_rendering(job)
            job.refresh_from_db()
            if job.stato == 'generato':
                url = f'/media/{job.immagine_path}'
                self.message_user(
                    request,
                    format_html('Anteprima di «{}» generata: <a href="{}" target="_blank">{}</a>', template.nome, url, url),
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request, f'Anteprima di «{template.nome}» fallita: {job.errore_messaggio}', messages.ERROR,
                )


class DestinazioneForm(forms.ModelForm):
    access_token = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False),
        help_text='Lasciare vuoto per non modificare il token esistente.',
    )

    class Meta:
        model = Destinazione
        fields = ['client_id', 'piattaforma', 'page_id', 'nome_descrittivo']

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk and not cleaned_data.get('access_token'):
            self.add_error('access_token', 'Il token è obbligatorio alla creazione.')
        return cleaned_data

    def save(self, commit=True):
        destinazione = super().save(commit=False)
        token = self.cleaned_data.get('access_token')
        if token:
            destinazione.access_token = token
        if commit:
            destinazione.save()
        return destinazione


@admin.register(Destinazione)
class DestinazioneAdmin(admin.ModelAdmin):
    form = DestinazioneForm
    list_display = ['nome_descrittivo', 'piattaforma', 'client_id', 'page_id', 'updated_at']
    list_filter = ['piattaforma']
    search_fields = ['nome_descrittivo', 'client_id', 'page_id']


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['id', 'client_id', 'template', 'stato_colorato', 'destinazione', 'created_at']
    list_filter = ['stato', 'destinazione__piattaforma']
    search_fields = ['client_id', 'post_id_risultante']
    readonly_fields = [
        'client_id', 'template', 'dati', 'stato', 'immagine_path', 'destinazione', 'caption',
        'post_id_risultante', 'errore_messaggio', 'created_at', 'updated_at',
    ]

    def stato_colorato(self, obj):
        colori = {'in_coda': '#888', 'generato': '#2563eb', 'pubblicato': '#16a34a', 'errore': '#dc2626'}
        return format_html('<b style="color:{}">{}</b>', colori.get(obj.stato, '#000'), obj.get_stato_display())
    stato_colorato.short_description = 'Stato'

    def has_add_permission(self, request):
        # I Job nascono solo dalle API (/genera, /pubblica) o dall'azione
        # "Genera anteprima" su Template: niente creazione manuale in admin.
        return False
