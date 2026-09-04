"""
Django settings for postnect project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')


SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-bg@(&2yns!o2mek_v77^i!b!8l#c7yj1r1%^gv1)1%ydryig^@',
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() == 'true'

ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]

# Token condiviso per la API interna di gestione utenti (accounts/), usata
# dal Portale per creare/modificare/eliminare account da remoto. L'endpoint
# è raggiungibile solo da localhost (regola Nginx), il token è una difesa
# aggiuntiva. Generarlo con: python -c "import secrets; print(secrets.token_urlsafe(32))"
INTERNAL_API_TOKEN = os.environ.get('INTERNAL_API_TOKEN', '')

# Anagrafica clienti condivisa: vive nel Portale (clienti/api/internal/),
# qui teniamo solo il client_id (UUID) su Template/Destinazione/Job/ApiClient
# e risolviamo nome/dati chiamando questa API in tempo reale (jobs/portal_client.py).
# Generare PORTAL_API_TOKEN con lo stesso valore di INTERNAL_API_TOKEN nel
# .env del Portale.
PORTAL_INTERNAL_BASE_URL = os.environ.get('PORTAL_INTERNAL_BASE_URL', '')
PORTAL_API_TOKEN = os.environ.get('PORTAL_API_TOKEN', '')
# URL pubblico del Portale, solo per link "torna al Portale" in UI.
PORTAL_PUBLIC_URL = os.environ.get('PORTAL_PUBLIC_URL', '')
# Percorso del certificato (self-signed, es. /etc/ssl/portal/selfsigned.crt)
# usato per verificare la connessione TLS verso PORTAL_INTERNAL_BASE_URL, al
# posto di disattivare del tutto la verifica. Vuoto in locale, dove
# PORTAL_INTERNAL_BASE_URL punta tipicamente a un URL http:// di sviluppo.
PORTAL_INTERNAL_CA_CERT = os.environ.get('PORTAL_INTERNAL_CA_CERT', '')

# Cifratura a riposo dell'access_token delle Destinazioni (Fernet). Stesso
# nome env usato da FBOMailer/FBOLeads. Generare con:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MASTER_ENCRYPTION_KEY = os.environ.get('MASTER_ENCRYPTION_KEY', '')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'jobs',
    'accounts',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'postnect.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'jobs.context_processors.portal_public_url',
            ],
        },
    },
]

WSGI_APPLICATION = 'postnect.wsgi.application'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'job-list'
LOGOUT_REDIRECT_URL = 'login'


# Database — SQLite: coerente col resto della famiglia FBO, volumi previsti
# bassi (job di generazione/pubblicazione, non scritture concorrenti massive).

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

if not DEBUG:
    # Il VPS è dietro Nginx che termina TLS e inoltra a Gunicorn su
    # localhost: senza questo header Django non saprebbe che la richiesta
    # originale era HTTPS.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization

LANGUAGE_CODE = 'it-it'

TIME_ZONE = 'Europe/Rome'

USE_I18N = True

USE_TZ = True


# Static & media files

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Immagini generate dal motore di rendering (Prompt 2) finiscono qui.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Celery — coda per rendering (Playwright) e pubblicazione (Prompt 2/3), mai
# eseguiti in request-response diretto. Redis condiviso con le altre app
# della VPS: db diverso per non collidere con le code altrui (vedi
# struttura_app_fbo.md per l'allocazione nota — verificare comunque sul VPS
# prima del primo deploy).
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/3')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/3')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
