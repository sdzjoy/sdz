from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False
PUBLIC_SITE_ORIGIN = os.getenv("PUBLIC_SITE_ORIGIN", "https://sdzjoy.com")
WWW_REDIRECT_HOST = os.getenv("WWW_REDIRECT_HOST", "www.sdzjoy.com")

if SECRET_KEY == DEVELOPMENT_SECRET_SENTINEL:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production")

if not os.getenv("DJANGO_ALLOWED_HOSTS"):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production")

if not os.getenv("POSTGRES_PASSWORD"):
    raise ImproperlyConfigured("POSTGRES_PASSWORD must be set in production")

if ACCOUNT_EMAIL_VERIFICATION not in {"mandatory", "optional", "none"}:
    raise ImproperlyConfigured(
        "ACCOUNT_EMAIL_VERIFICATION must be mandatory, optional, or none"
    )

TURNSTILE_REQUIRED = True
if not TURNSTILE_EXPECTED_HOSTNAMES:
    TURNSTILE_EXPECTED_HOSTNAMES = ["sdzjoy.com", "id.sdzjoy.com"]
for required_setting in (
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "MFA_ENCRYPTION_KEY",
    "IDP_OIDC_PRIVATE_KEY",
):
    if not globals()[required_setting]:
        raise ImproperlyConfigured(f"{required_setting} must be set in production")

DATABASES["default"] = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.getenv("POSTGRES_DB", "sdzjoy"),
    "USER": os.getenv("POSTGRES_USER", "sdzjoy"),
    "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
    "HOST": os.getenv("POSTGRES_HOST", "db"),
    "PORT": os.getenv("POSTGRES_PORT", "5432"),
    "CONN_MAX_AGE": 60,
    "CONN_HEALTH_CHECKS": True,
}

STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
}

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
