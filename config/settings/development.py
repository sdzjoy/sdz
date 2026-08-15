from .base import *

DEBUG = True

if os.getenv("POSTGRES_HOST"):
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "sdzjoy"),
        "USER": os.getenv("POSTGRES_USER", "sdzjoy"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0,
    }

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = True
