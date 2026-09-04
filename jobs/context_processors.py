from django.conf import settings


def portal_public_url(request):
    return {'PORTAL_PUBLIC_URL': getattr(settings, 'PORTAL_PUBLIC_URL', '')}
