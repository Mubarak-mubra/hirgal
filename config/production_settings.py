"""Production settings. All deployment secrets and service endpoints come from env."""

import os
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Set the {name} environment variable for production.")
    return value


def _csv(name):
    return [value.strip() for value in os.environ.get(name, "").split(",") if value.strip()]


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = False
SECRET_KEY = _required("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters.")

ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set DJANGO_ALLOWED_HOSTS to explicit production hostnames.")

CSRF_TRUSTED_ORIGINS = _csv("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("Set DJANGO_CSRF_TRUSTED_ORIGINS to the HTTPS origin(s) for this site.")
if any(
    urlparse(origin).scheme != "https" or not urlparse(origin).hostname
    for origin in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured("Every DJANGO_CSRF_TRUSTED_ORIGINS entry must be an HTTPS origin.")

database_url = urlparse(_required("DATABASE_URL"))
if database_url.scheme not in {"postgres", "postgresql"}:
    raise ImproperlyConfigured("Production DATABASE_URL must use PostgreSQL.")

database_name = unquote(database_url.path.lstrip("/"))
database_user = unquote(database_url.username or "")
database_host = database_url.hostname or ""
if not all((database_name, database_user, database_host)):
    raise ImproperlyConfigured("DATABASE_URL must include a database name, username, and hostname.")

database_options = parse_qs(database_url.query)
DATABASES = {  # noqa: F405
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": database_user,
        "PASSWORD": unquote(database_url.password or ""),
        "HOST": database_host,
        "PORT": database_url.port or 5432,
        "CONN_MAX_AGE": int(os.environ.get("DATABASE_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "sslmode": os.environ.get(
                "DATABASE_SSLMODE", database_options.get("sslmode", ["require"])[0]
            ),
        },
    },
}

SECURE_SSL_REDIRECT = _bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = _bool("SECURE_HSTS_PRELOAD", False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if _bool("TRUST_X_FORWARDED_PROTO", True):
    # Use only when the trusted hosting proxy overwrites this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
