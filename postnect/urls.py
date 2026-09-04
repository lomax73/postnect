"""
URL configuration for postnect project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/internal/', include('accounts.urls')),
    path('', include('jobs.urls')),
    # Postnect non ha un frontend pubblico: la radice serve solo da entry
    # point per l'uso interno (Django admin), è dove punta la card nel
    # Portale FBO.
    path('', RedirectView.as_view(url='admin/', permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
