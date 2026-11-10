"""Validated deployment configuration; local development requires a secret too."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a private random value.")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
CSRF_TRUSTED_ORIGINS = list(filter(None, os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")))
TIME_ZONE = os.environ.get("SCHOOL_TIME_ZONE", "America/Chicago")
ZoneInfo(TIME_ZONE)
USE_TZ = True
LANGUAGE_CODE = "en-us"
DEFAULT_SCHOOL = os.environ.get("SCHOOL", "NORTHEAST_ELEMENTARY")
DEFAULT_GRADE = os.environ.get("GRADE", "01")
# Checked against Northeast Elementary weekly menus for grades 01 through 05.
SUPPORTED_GRADES = os.environ.get("SUPPORTED_GRADES", "01,02,03,04,05").split(",")
if DEFAULT_GRADE not in SUPPORTED_GRADES:
    raise ImproperlyConfigured("GRADE must be in SUPPORTED_GRADES")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "schoolcafe.sqlite3")),
        "OPTIONS": {
            "timeout": 5,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django_htmx",
    "schoolmenu",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "schoolmenu.config.urls"
WSGI_APPLICATION = "schoolmenu.config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
MENU_TTL = 900
EMPTY_MENU_TTL = 300
STALE_MENU_TTL = 86400
PROVIDER_TIMEOUT = 5
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
