from django.urls import path

from . import views

urlpatterns = [
    path('genera', views.GeneraView.as_view(), name='genera'),
    path('pubblica', views.PubblicaView.as_view(), name='pubblica'),
    path('job/<int:pk>/', views.JobDetailView.as_view(), name='job-detail'),
]
