from pathlib import Path
from corsheaders.defaults import default_headers
from django.core.management.utils import get_random_secret_key
import os

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"

# --- SECRET_KEY sin hardcodear ---
_env_secret = os.getenv("DJANGO_SECRET_KEY")

# --- SECRET_KEY se encuentra ahora dentro del .env en local ---
if _env_secret:
    SECRET_KEY = _env_secret
else:
    if DEBUG:
        # En desarrollo genera una clave aleatoria cada vez
        SECRET_KEY = get_random_secret_key()
    else:
        # En producción obligamos a que exista la variable
        raise ValueError("DJANGO_SECRET_KEY environment variable not set")
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # Stats app: use top-level `stats` package (consolidated)
    "stats",
    "corsheaders",
]

MIGRATION_MODULES = {
    'stats': 'stats.migrations',
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend_estadisticas.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend_estadisticas.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "es-es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CORS_ALLOW_CREDENTIALS = True


CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-user-role",
    "x-dev-user",
    "authorization",
]

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
