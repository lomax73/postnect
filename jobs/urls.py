from django.urls import path

from . import api_views, dashboard_views

urlpatterns = [
    # API esterna (X-API-Key)
    path('genera', api_views.GeneraView.as_view(), name='genera'),
    path('pubblica', api_views.PubblicaView.as_view(), name='pubblica'),
    path('job/<int:pk>/', api_views.JobDetailView.as_view(), name='job-detail'),

    # Dashboard interna (login richiesto)
    path('', dashboard_views.JobListView.as_view(), name='job-list'),
    path('job/<int:pk>/elimina/', dashboard_views.JobDeleteView.as_view(), name='job-delete'),
    path('job/<int:pk>/pubblica/', dashboard_views.JobPubblicaView.as_view(), name='job-pubblica'),

    path('templates/', dashboard_views.TemplateListView.as_view(), name='template-list'),
    path('templates/nuovo/', dashboard_views.TemplateCreateView.as_view(), name='template-create'),
    path('templates/<int:pk>/modifica/', dashboard_views.TemplateUpdateView.as_view(), name='template-update'),
    path('templates/<int:pk>/elimina/', dashboard_views.TemplateDeleteView.as_view(), name='template-delete'),
    path('templates/<int:pk>/anteprima/', dashboard_views.TemplateAnteprimaView.as_view(), name='template-anteprima'),

    path('destinazioni/', dashboard_views.DestinazioneListView.as_view(), name='destinazione-list'),
    path('destinazioni/nuova/', dashboard_views.DestinazioneCreateView.as_view(), name='destinazione-create'),
    path('destinazioni/<int:pk>/modifica/', dashboard_views.DestinazioneUpdateView.as_view(), name='destinazione-update'),
    path('destinazioni/<int:pk>/elimina/', dashboard_views.DestinazioneDeleteView.as_view(), name='destinazione-delete'),

    path('client-api/', dashboard_views.ApiClientListView.as_view(), name='apiclient-list'),
    path('client-api/nuovo/', dashboard_views.ApiClientCreateView.as_view(), name='apiclient-create'),
    path('client-api/<int:pk>/elimina/', dashboard_views.ApiClientDeleteView.as_view(), name='apiclient-delete'),
    path('client-api/<int:pk>/rigenera/', dashboard_views.ApiClientRigeneraView.as_view(), name='apiclient-rigenera'),
    path('client-api/<int:pk>/sospendi/', dashboard_views.ApiClientSospendiView.as_view(), name='apiclient-sospendi'),
]
