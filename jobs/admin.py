from django.contrib import admin

from .models import ApiClient, Destinazione, Job, Template

# Registrazione minima per lo scaffolding (Prompt 1). La dashboard vera
# (list_display, filtri, mascheramento token, azione "genera anteprima") è
# oggetto del Prompt 4.
admin.site.register(ApiClient)
admin.site.register(Template)
admin.site.register(Destinazione)
admin.site.register(Job)
