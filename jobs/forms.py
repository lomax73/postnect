from django import forms

from .models import ApiClient, Destinazione, Template


class TemplateForm(forms.ModelForm):
    campi_richiesti_csv = forms.CharField(
        label='Campi richiesti', required=False,
        help_text='Elenco separato da virgole dei placeholder attesi nei dati del Job, es: avversario, risultato, data',
        widget=forms.TextInput(attrs={'placeholder': 'avversario, risultato, data'}),
    )

    class Meta:
        model = Template
        fields = ['client_id', 'nome', 'html_content', 'css_content', 'larghezza', 'altezza', 'attivo']
        widgets = {
            'html_content': forms.Textarea(attrs={'rows': 10, 'class': 'mono'}),
            'css_content': forms.Textarea(attrs={'rows': 6, 'class': 'mono'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['campi_richiesti_csv'].initial = ', '.join(self.instance.campi_richiesti)

    def clean_campi_richiesti_csv(self):
        valore = self.cleaned_data.get('campi_richiesti_csv', '')
        return [campo.strip() for campo in valore.split(',') if campo.strip()]

    def save(self, commit=True):
        template = super().save(commit=False)
        template.campi_richiesti = self.cleaned_data['campi_richiesti_csv']
        if commit:
            template.save()
        return template


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


class ApiClientForm(forms.ModelForm):
    class Meta:
        model = ApiClient
        fields = ['client_id', 'attivo']
